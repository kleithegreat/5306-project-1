"""M2: profile the snapshot's actual schema into docs/data-dictionary.md.

Everything is measured from data/interim/*.parquet. Nothing is copied from the
published column descriptions, so the output says what this snapshot contains
rather than what it is supposed to contain.

Usage: python src/profile_schema.py
"""

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "docs" / "data-dictionary.md"

TABLES = ["notes", "noteStatusHistory", "userEnrollment"]
CATEGORICAL_MAX = 40
EPOCH_MS_RANGE = (1_000_000_000_000, 2_000_000_000_000)


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def src(table: str) -> str:
    return f"read_parquet('{INTERIM / f'{table}.parquet'}')"


def profile_table(con: duckdb.DuckDBPyConnection, table: str) -> dict:
    cols = con.execute(f"DESCRIBE SELECT * FROM {src(table)}").fetchall()
    names = [c[0] for c in cols]
    types = {c[0]: c[1] for c in cols}

    parts = ["count(*) AS n_rows"]
    for i, name in enumerate(names):
        c = q(name)
        parts += [f"count({c}) AS nn_{i}", f"count(DISTINCT {c}) AS nd_{i}"]
        if types[name] == "VARCHAR":
            parts += [f"min(length({c})) AS lo_{i}", f"max(length({c})) AS hi_{i}"]
        else:
            parts += [f"min({c}) AS lo_{i}", f"max({c}) AS hi_{i}"]
    row = con.execute(f"SELECT {', '.join(parts)} FROM {src(table)}").fetchone()

    n_rows = row[0]
    profile = {"rows": n_rows, "columns": []}
    for i, name in enumerate(names):
        nn, nd, lo, hi = row[1 + 4 * i : 5 + 4 * i]
        col = {
            "name": name,
            "type": types[name],
            "nulls": n_rows - nn,
            "null_rate": (n_rows - nn) / n_rows if n_rows else 0.0,
            "distinct": nd,
            "min": lo,
            "max": hi,
        }
        if 0 < nd <= CATEGORICAL_MAX:
            col["values"] = con.execute(
                f"SELECT {q(name)}, count(*) FROM {src(table)} "
                f"WHERE {q(name)} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
            ).fetchall()
        if types[name] == "BIGINT" and isinstance(hi, int) and EPOCH_MS_RANGE[0] <= hi <= EPOCH_MS_RANGE[1]:
            col["as_dates"] = con.execute(
                f"SELECT epoch_ms(min({q(name)}))::DATE, epoch_ms(max({q(name)}))::DATE "
                f"FROM {src(table)} WHERE {q(name)} > 0"
            ).fetchone()
        profile["columns"].append(col)
    return profile


def author_columns(profile: dict) -> list[str]:
    return [c["name"] for c in profile["columns"] if "participantid" in c["name"].lower()]


def cross_table_checks(con: duckdb.DuckDBPyConnection, profiles: dict) -> list[str]:
    flags = []

    ids = {t: author_columns(p) for t, p in profiles.items()}
    flags.append(
        "Author identifier column: "
        + "; ".join(f"`{t}`.{'/'.join(c) or '—'}" for t, c in ids.items())
        + "."
    )

    disagree = con.execute(
        f"SELECT count(*) FROM {src('notes')} n JOIN {src('noteStatusHistory')} h USING (noteId) "
        "WHERE n.noteAuthorParticipantId IS DISTINCT FROM h.noteAuthorParticipantId"
    ).fetchone()[0]
    flags.append(
        f"`notes` and `noteStatusHistory` disagree on the author of **{disagree:,}** notes "
        f"joined on `noteId`."
    )

    only_notes, only_hist = con.execute(
        f"SELECT (SELECT count(*) FROM {src('notes')} n "
        f"        WHERE NOT EXISTS (SELECT 1 FROM {src('noteStatusHistory')} h WHERE h.noteId = n.noteId)), "
        f"       (SELECT count(*) FROM {src('noteStatusHistory')} h "
        f"        WHERE NOT EXISTS (SELECT 1 FROM {src('notes')} n WHERE n.noteId = h.noteId))"
    ).fetchone()
    flags.append(
        f"Notes in `notes` with no `noteStatusHistory` row: **{only_notes:,}** — these have no "
        f"recorded outcome at all, which is not the same as never leaving NMR. "
        f"Rows in `noteStatusHistory` with no `notes` row: **{only_hist:,}** (expected — "
        f"deleted notes keep their status history)."
    )

    unenrolled = con.execute(
        f"SELECT count(*) FROM (SELECT DISTINCT noteAuthorParticipantId a FROM {src('notes')}) "
        f"WHERE NOT EXISTS (SELECT 1 FROM {src('userEnrollment')} e WHERE e.participantId = a)"
    ).fetchone()[0]
    flags.append(f"Note authors with no row in `userEnrollment`: **{unenrolled:,}**.")

    return flags


def column_flags(profiles: dict) -> list[str]:
    flags = []
    for table, p in profiles.items():
        empty = [c["name"] for c in p["columns"] if c["distinct"] == 0]
        if empty:
            flags.append(f"`{table}`: entirely null — {', '.join(f'`{c}`' for c in empty)}.")
        constant = [c["name"] for c in p["columns"] if c["distinct"] == 1]
        if constant:
            flags.append(
                f"`{table}`: one distinct value only — {', '.join(f'`{c}`' for c in constant)}."
            )
        high_null = [
            (c["name"], c["null_rate"])
            for c in p["columns"]
            if c["distinct"] > 1 and c["null_rate"] > 0.5
        ]
        if high_null:
            flags.append(
                f"`{table}`: over half null — "
                + ", ".join(f"`{n}` ({r:.1%})" for n, r in sorted(high_null, key=lambda x: -x[1]))
                + "."
            )
    return flags


def fmt_summary(col: dict) -> str:
    if col["distinct"] == 0:
        return "—"
    if "values" in col and col["distinct"] <= 8:
        return ", ".join(f"`{v}` {n:,}" for v, n in col["values"])
    if "as_dates" in col:
        lo, hi = col["as_dates"]
        return f"{lo} … {hi}"
    if col["type"] == "VARCHAR":
        return f"length {col['min']}–{col['max']}"
    return f"{col['min']:,} … {col['max']:,}"


def render(snapshot: str, profiles: dict, flags: list[str]) -> str:
    L = [
        "# Data dictionary (M2)",
        "",
        f"Snapshot **{snapshot}**. Generated by `src/profile_schema.py` from",
        "`data/interim/*.parquet`. Do not hand-edit — rerun the script.",
        "",
        "Every figure here is measured from this snapshot, not copied from the published",
        "column descriptions, so it says what the data contains rather than what it should.",
        "Interpretation of these numbers lives in `docs/worklog.md`.",
        "",
        "## Flags",
        "",
    ]
    L += [f"- {f}" for f in flags]

    for table, p in profiles.items():
        L += [
            "",
            f"## {table}",
            "",
            f"{p['rows']:,} rows, {len(p['columns'])} columns.",
            "",
            "| column | type | null % | distinct | range / values |",
            "| --- | --- | ---: | ---: | --- |",
        ]
        for c in p["columns"]:
            L.append(
                f"| `{c['name']}` | {c['type']} | {c['null_rate']:.1%} | "
                f"{c['distinct']:,} | {fmt_summary(c)} |"
            )

        wide = [c for c in p["columns"] if "values" in c and c["distinct"] > 8]
        if wide:
            L += ["", f"### {table} — value counts", ""]
            for c in wide:
                L += [f"`{c['name']}` ({c['distinct']} values, {c['null_rate']:.1%} null)", ""]
                L += [f"- `{v}` — {n:,}" for v, n in c["values"]]
                L.append("")
    return "\n".join(L).rstrip() + "\n"


def main() -> None:
    snapshot = json.loads((INTERIM / "row_counts.json").read_text())["snapshot"]
    con = duckdb.connect()
    profiles = {t: profile_table(con, t) for t in TABLES}
    flags = cross_table_checks(con, profiles) + column_flags(profiles)
    OUT.write_text(render(snapshot, profiles, flags))
    print(f"wrote {OUT.relative_to(ROOT)}")
    for f in flags:
        print("  -", f)


if __name__ == "__main__":
    main()
