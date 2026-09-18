"""M0 follow-up: do author identifiers stay the same across two upstream releases?

The analysis assumes a participant ID means the same person in every snapshot. Upstream
keeps roughly a week of snapshots, so this can only be checked while a second one is
still downloadable. Compares noteStatusHistory, which carries the author of every scored
note including deleted ones, across two releases.

Usage: python src/check_id_stability.py <other_snapshot_date>
"""

import json
import sys
import zipfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
HIST = f"read_parquet('{INTERIM / 'noteStatusHistory.parquet'}')"


def main() -> None:
    other = sys.argv[1]
    snapshot = json.loads((INTERIM / "row_counts.json").read_text())["snapshot"]
    raw = ROOT / "data" / "raw" / other
    tsv = INTERIM / "tsv" / other
    tsv.mkdir(parents=True, exist_ok=True)

    for zpath in sorted(raw.glob("noteStatusHistory-*.zip")):
        with zipfile.ZipFile(zpath) as zf:
            for info in zf.infolist():
                out = tsv / info.filename
                if not (out.exists() and out.stat().st_size == info.file_size):
                    zf.extract(info, tsv)

    files = "[" + ", ".join(f"'{p}'" for p in sorted(tsv.glob("noteStatusHistory-*.tsv"))) + "]"
    older = (
        f"(SELECT * FROM read_csv({files}, delim='\\t', header=true, quote='', "
        f"escape='', sample_size=-1))"
    )

    con = duckdb.connect()
    shared, mismatched = con.execute(
        f"""
        SELECT count(*), count(*) FILTER (
          WHERE a.noteAuthorParticipantId IS DISTINCT FROM b.noteAuthorParticipantId)
        FROM {HIST} a JOIN {older} b USING (noteId)
        """
    ).fetchone()
    only_new, only_old = con.execute(
        f"""
        SELECT (SELECT count(*) FROM {HIST} a
                WHERE NOT EXISTS (SELECT 1 FROM {older} b WHERE b.noteId = a.noteId)),
               (SELECT count(*) FROM {older} b
                WHERE NOT EXISTS (SELECT 1 FROM {HIST} a WHERE a.noteId = b.noteId))
        """
    ).fetchone()

    print(f"comparing {snapshot} against {other}")
    print(f"  notes in both releases:        {shared:,}")
    print(f"  author ID differs:             {mismatched:,}")
    print(f"  only in {snapshot}:            {only_new:,}")
    print(f"  only in {other}:            {only_old:,}")
    print("  RESULT:", "author IDs are stable" if mismatched == 0 else "AUTHOR IDS ARE NOT STABLE")


if __name__ == "__main__":
    main()
