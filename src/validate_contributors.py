"""M4: validate data/processed/contributors.parquet and write docs/validation.md.

The hand-check rebuilds 20 randomly chosen authors from the raw TSVs with a separate
code path, so a bug shared by the build query and the checks cannot hide in both.

Usage: python src/validate_contributors.py
"""

import csv
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
TSV = INTERIM / "tsv"
TABLE = ROOT / "data" / "processed" / "contributors.parquet"
OUT = ROOT / "docs" / "validation.md"

SAMPLE_SEED = "5306-project-1"
SAMPLE_N = 20

csv.field_size_limit(sys.maxsize)

C = f"read_parquet('{TABLE}')"
NOTES = f"read_parquet('{INTERIM / 'notes.parquet'}')"
HIST = f"read_parquet('{INTERIM / 'noteStatusHistory.parquet'}')"


def check(name: str, got, want, detail: str = "") -> dict:
    return {"name": name, "got": got, "want": want, "pass": got == want, "detail": detail}


def tsv_line_counts() -> dict[str, int]:
    counts = {}
    for path in sorted(TSV.glob("*.tsv")):
        with open(path, "rb") as f:
            n = sum(buf.count(b"\n") for buf in iter(lambda: f.read(1 << 22), b""))
        counts[path.name] = n - 1
    return counts


def structural_checks(con: duckdb.DuckDBPyConnection) -> list[dict]:
    lines = tsv_line_counts()
    checks = [
        check(
            "TSV newline count matches Parquet row count (notes)",
            sum(v for k, v in lines.items() if k.startswith("notes-")),
            con.execute(f"SELECT count(*) FROM {NOTES}").fetchone()[0],
            "if note text contained raw newlines these would diverge",
        ),
        check(
            "TSV newline count matches Parquet row count (noteStatusHistory)",
            sum(v for k, v in lines.items() if k.startswith("noteStatusHistory-")),
            con.execute(f"SELECT count(*) FROM {HIST}").fetchone()[0],
        ),
        check(
            "1. distinct authors in contributors == distinct authors in notes",
            con.execute(f"SELECT count(DISTINCT author_id) FROM {C}").fetchone()[0],
            con.execute(f"SELECT count(DISTINCT noteAuthorParticipantId) FROM {NOTES}").fetchone()[0],
        ),
        check(
            "1b. one row per author",
            con.execute(f"SELECT count(*) FROM {C}").fetchone()[0],
            con.execute(f"SELECT count(DISTINCT author_id) FROM {C}").fetchone()[0],
        ),
        check(
            "2. sum(n_notes_total) == total notes",
            con.execute(f"SELECT sum(n_notes_total) FROM {C}").fetchone()[0],
            con.execute(f"SELECT count(*) FROM {NOTES}").fetchone()[0],
        ),
        check(
            "3. no second_note_at before first_note_at",
            con.execute(f"SELECT count(*) FROM {C} WHERE second_note_at < first_note_at").fetchone()[0],
            0,
        ),
        check(
            "4. first_verdict_at null exactly when first_verdict_status null",
            con.execute(
                f"SELECT count(*) FROM {C} "
                "WHERE (first_verdict_at IS NULL) <> (first_verdict_status IS NULL)"
            ).fetchone()[0],
            0,
        ),
        check(
            "5. no first_verdict_at before first_note_at",
            con.execute(f"SELECT count(*) FROM {C} WHERE first_verdict_at < first_note_at").fetchone()[0],
            0,
            "investigate before proceeding if non-zero; do not drop silently",
        ),
        check(
            "timestamp columns agree with the raw millis they were converted from",
            con.execute(
                f"SELECT count(*) FROM {C} WHERE "
                "epoch_ms(first_note_at_millis) IS DISTINCT FROM first_note_at "
                "OR epoch_ms(first_verdict_at_millis) IS DISTINCT FROM first_verdict_at "
                "OR epoch_ms(second_note_at_millis) IS DISTINCT FROM second_note_at"
            ).fetchone()[0],
            0,
        ),
        check(
            "an author with n_notes_total = 1 has no second note, and vice versa",
            con.execute(
                f"SELECT count(*) FROM {C} WHERE (n_notes_total = 1) <> (second_note_at IS NULL)"
            ).fetchone()[0],
            0,
        ),
        check(
            "cohort_month agrees with first_note_at",
            con.execute(
                f"SELECT count(*) FROM {C} WHERE cohort_month <> strftime(first_note_at, '%Y-%m')"
            ).fetchone()[0],
            0,
        ),
        check(
            "unscored first notes carry no verdict",
            con.execute(
                f"SELECT count(*) FROM {C} WHERE NOT first_note_scored AND first_verdict_status IS NOT NULL"
            ).fetchone()[0],
            0,
        ),
    ]
    return checks


def verdict_timing(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    return con.execute(
        f"""
        SELECT cohort_month[1:4] AS year,
               count(*) AS authors,
               count(*) FILTER (WHERE NOT first_note_scored) AS unscored,
               count(*) FILTER (WHERE first_note_scored AND first_verdict_status IS NULL) AS never_left_nmr,
               count(*) FILTER (WHERE first_verdict_status = 'CURRENTLY_RATED_HELPFUL') AS helpful,
               count(*) FILTER (WHERE first_verdict_status = 'CURRENTLY_RATED_NOT_HELPFUL') AS not_helpful,
               median(date_diff('second', first_note_at, first_verdict_at) / 86400.0) AS med_days,
               quantile_cont(date_diff('second', first_note_at, first_verdict_at) / 86400.0, 0.9) AS p90_days
        FROM {C} GROUP BY 1 ORDER BY 1
        """
    ).fetchall()


def sample_authors(con: duckdb.DuckDBPyConnection) -> list[str]:
    return [
        r[0]
        for r in con.execute(
            f"SELECT author_id FROM {C} ORDER BY md5(author_id || '{SAMPLE_SEED}') LIMIT {SAMPLE_N}"
        ).fetchall()
    ]


def scan_tsv(path_glob: str, key_col: str, keys: set[str]) -> list[dict]:
    hits = []
    for path in sorted(TSV.glob(path_glob)):
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
            header = next(reader)
            idx = header.index(key_col)
            for row in reader:
                if row[idx] in keys:
                    hits.append(dict(zip(header, row)))
    return hits


def rebuild_from_tsv(authors: list[str]) -> dict[str, dict]:
    """Recompute each sampled author's row straight from the TSVs."""
    wanted = set(authors)
    note_rows = scan_tsv("notes-*.tsv", "noteAuthorParticipantId", wanted)

    by_author: dict[str, list[dict]] = {a: [] for a in authors}
    for r in note_rows:
        by_author[r["noteAuthorParticipantId"]].append(r)

    first_ids = set()
    for rows in by_author.values():
        rows.sort(key=lambda r: (int(r["createdAtMillis"]), int(r["noteId"])))
        first_ids.add(rows[0]["noteId"])
    hist = {r["noteId"]: r for r in scan_tsv("noteStatusHistory-*.tsv", "noteId", first_ids)}

    tags = [
        k
        for k in note_rows[0]
        if k.startswith(("misleading", "notMisleading")) or k == "trustworthySources"
    ]

    rebuilt = {}
    for author, rows in by_author.items():
        first = rows[0]
        h = hist.get(first["noteId"])
        status = (h or {}).get("firstNonNMRStatus") or None
        vts = (h or {}).get("timestampMillisOfFirstNonNMRStatus") or None
        rebuilt[author] = {
            "first_note_id": int(first["noteId"]),
            "first_note_at_millis": int(first["createdAtMillis"]),
            "first_note_scored": h is not None,
            "first_verdict_status": status,
            "first_verdict_at_millis": int(vts) if vts else None,
            "second_note_at_millis": int(rows[1]["createdAtMillis"]) if len(rows) > 1 else None,
            "n_notes_total": len(rows),
            "first_classification": first["classification"] or None,
            "first_has_url": "http" in first["summary"].lower(),
            "first_note_len": len(first["summary"]),
            "first_reason_tags": sorted(t for t in tags if first[t] == "1"),
        }
    return rebuilt


def hand_check(con: duckdb.DuckDBPyConnection, authors: list[str]) -> list[dict]:
    expected = rebuild_from_tsv(authors)
    ids = ", ".join(f"'{a}'" for a in authors)
    cols = list(next(iter(expected.values())).keys())
    actual = {
        r[0]: dict(zip(cols, r[1:]))
        for r in con.execute(
            f"SELECT author_id, {', '.join(cols)} FROM {C} WHERE author_id IN ({ids})"
        ).fetchall()
    }
    cases = []
    for author in authors:
        want, got = expected[author], actual[author]
        fields = []
        for c in cols:
            w, g = want[c], got[c]
            if c == "first_reason_tags":
                g = sorted(g)
            fields.append({"field": c, "tsv": w, "table": g, "pass": w == g})
        cases.append({"author": author, "fields": fields, "pass": all(f["pass"] for f in fields)})
    return cases


def render(snapshot: str, checks: list[dict], timing: list[tuple], cases: list[dict]) -> str:
    failed = [c for c in checks if not c["pass"]]
    bad_cases = [c for c in cases if not c["pass"]]

    L = [
        "# Validation (M4)",
        "",
        f"Snapshot **{snapshot}**. Generated by `src/validate_contributors.py`.",
        "Do not hand-edit — rerun the script.",
        "",
    ]
    if failed or bad_cases:
        L += [
            f"## FAILURES: {len(failed)} check(s), {len(bad_cases)} hand-checked author(s)",
            "",
            "Do not pass HUMAN GATE 2 until these are explained.",
            "",
        ]
    else:
        L += ["All checks pass and all 20 hand-checked authors match the raw TSVs.", ""]

    L += ["## Checks", "", "| check | result | expected | ok |", "| --- | ---: | ---: | :-: |"]
    for c in checks:
        L.append(f"| {c['name']} | {c['got']:,} | {c['want']:,} | {'✓' if c['pass'] else '**✗**'} |")
    notes = [c for c in checks if c["detail"]]
    if notes:
        L += [""] + [f"- *{c['name']}*: {c['detail']}" for c in notes]

    L += [
        "",
        "## 6. First-note outcome and verdict timing, by cohort year",
        "",
        "`unscored` is first notes with no `noteStatusHistory` row at all — no recorded",
        "outcome, which is not the same as never leaving NMR. Timing is days from note",
        "creation to first verdict, over first notes that got one.",
        "",
        "| year | authors | unscored | never left NMR | Helpful | Not Helpful | median days | p90 days |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for yr, a, un, nmr, h, nh, med, p90 in timing:
        f = lambda v: "—" if v is None else f"{v:.2f}"
        L.append(f"| {yr} | {a:,} | {un:,} | {nmr:,} | {h:,} | {nh:,} | {f(med)} | {f(p90)} |")

    L += [
        "",
        "## 7. Twenty hand-checked authors",
        "",
        f"Sampled deterministically (`ORDER BY md5(author_id || '{SAMPLE_SEED}')`), rebuilt",
        "field by field from the raw TSVs by a separate code path, and compared against the",
        "table. `tsv` is what the raw files say; `table` is what `contributors.parquet` says.",
        "",
    ]
    for i, case in enumerate(cases, 1):
        L += [
            f"### {i}. `{case['author']}` — {'all fields match' if case['pass'] else '**MISMATCH**'}",
            "",
            "| field | tsv | table | ok |",
            "| --- | --- | --- | :-: |",
        ]
        for f in case["fields"]:
            L.append(f"| `{f['field']}` | `{f['tsv']}` | `{f['table']}` | {'✓' if f['pass'] else '**✗**'} |")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def main() -> None:
    snapshot = json.loads((INTERIM / "row_counts.json").read_text())["snapshot"]
    con = duckdb.connect()
    checks = structural_checks(con)
    timing = verdict_timing(con)
    authors = sample_authors(con)
    cases = hand_check(con, authors)
    OUT.write_text(render(snapshot, checks, timing, cases))

    failed = [c["name"] for c in checks if not c["pass"]]
    bad = [c["author"] for c in cases if not c["pass"]]
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"checks: {len(checks) - len(failed)}/{len(checks)} pass")
    for name in failed:
        print("  FAILED:", name)
    print(f"hand-checked authors: {len(cases) - len(bad)}/{len(cases)} match")
    for a in bad:
        print("  MISMATCH:", a)


if __name__ == "__main__":
    main()
