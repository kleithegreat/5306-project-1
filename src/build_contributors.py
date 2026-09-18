"""M3: one row per note author, describing their first note and what happened next.

Nothing is filtered here. Exclusions belong in M5 so they stay visible and reversible.

Usage: python src/build_contributors.py
"""

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "processed" / "contributors.parquet"

NOTES = f"read_parquet('{INTERIM / 'notes.parquet'}')"
HIST = f"read_parquet('{INTERIM / 'noteStatusHistory.parquet'}')"


def tag_columns(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Reason-tag columns, read from the snapshot rather than hardcoded."""
    names = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM {NOTES}").fetchall()]
    return [
        n
        for n in names
        if n.startswith(("misleading", "notMisleading")) or n == "trustworthySources"
    ]


def build(con: duckdb.DuckDBPyConnection, snapshot: str) -> None:
    tags = tag_columns(con)
    tag_list = ",\n            ".join(f'CASE WHEN "{t}" = 1 THEN \'{t}\' END' for t in tags)

    con.execute(
        f"""
        COPY (
          WITH ordered AS (
            SELECT
              noteAuthorParticipantId AS author_id,
              noteId, createdAtMillis, classification, summary,
              {', '.join(f'"{t}"' for t in tags)},
              row_number() OVER w AS rn,
              count(*) OVER (PARTITION BY noteAuthorParticipantId) AS n_notes_total,
              lead(createdAtMillis) OVER w AS second_note_at_millis
            FROM {NOTES}
            WINDOW w AS (PARTITION BY noteAuthorParticipantId ORDER BY createdAtMillis, noteId)
          ),
          cutoff AS (SELECT max(createdAtMillis) AS m FROM {NOTES})
          SELECT
            o.author_id,
            o.noteId                              AS first_note_id,
            epoch_ms(o.createdAtMillis)           AS first_note_at,
            strftime(epoch_ms(o.createdAtMillis), '%Y-%m') AS cohort_month,
            h.noteId IS NOT NULL                  AS first_note_scored,
            h.firstNonNMRStatus                   AS first_verdict_status,
            epoch_ms(h.timestampMillisOfFirstNonNMRStatus) AS first_verdict_at,
            epoch_ms(o.second_note_at_millis)     AS second_note_at,
            o.n_notes_total,
            o.classification                      AS first_classification,
            o.summary ILIKE '%http%'              AS first_has_url,
            length(o.summary)                     AS first_note_len,
            list_filter([
            {tag_list}
            ], x -> x IS NOT NULL)                AS first_reason_tags,
            DATE '{snapshot}'                     AS snapshot_at,
            epoch_ms(c.m)                         AS data_cutoff_at,
            o.createdAtMillis                     AS first_note_at_millis,
            h.timestampMillisOfFirstNonNMRStatus  AS first_verdict_at_millis,
            o.second_note_at_millis
          FROM ordered o
          LEFT JOIN {HIST} h ON h.noteId = o.noteId
          CROSS JOIN cutoff c
          WHERE o.rn = 1
          ORDER BY o.author_id
        ) TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )


def main() -> None:
    snapshot = json.loads((INTERIM / "row_counts.json").read_text())["snapshot"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    build(con, snapshot)

    rows, authors = con.execute(
        f"SELECT count(*), count(DISTINCT author_id) FROM read_parquet('{OUT}')"
    ).fetchone()
    expected = con.execute(
        f"SELECT count(DISTINCT noteAuthorParticipantId) FROM {NOTES}"
    ).fetchone()[0]
    print(f"wrote {OUT.relative_to(ROOT)}: {rows:,} rows, {authors:,} distinct authors")
    print(f"distinct authors in notes: {expected:,}" + ("  OK" if authors == expected else "  MISMATCH"))


if __name__ == "__main__":
    main()
