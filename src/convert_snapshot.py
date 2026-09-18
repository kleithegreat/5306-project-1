"""M0: unzip the raw snapshot and convert each table to Parquet.

Raw zips in data/raw/<snapshot>/ are never written to. TSVs are extracted to
data/interim/tsv/ and Parquet lands in data/interim/. Rerunnable: extraction is
skipped when the TSV already exists with the size the zip advertises, and Parquet
is always rewritten from the TSVs.

Usage: python src/convert_snapshot.py [snapshot_date]
"""

import json
import sys
import zipfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
TSV = INTERIM / "tsv"

TABLES = ["notes", "noteStatusHistory", "userEnrollment"]


def snapshot_dir(date: str | None) -> Path:
    if date:
        return RAW / date
    dirs = sorted(p for p in RAW.iterdir() if p.is_dir())
    if not dirs:
        raise SystemExit(f"no snapshot directories under {RAW}")
    return dirs[-1]


def extract(snap: Path) -> None:
    TSV.mkdir(parents=True, exist_ok=True)
    for zpath in sorted(snap.glob("*.zip")):
        with zipfile.ZipFile(zpath) as zf:
            for info in zf.infolist():
                out = TSV / info.filename
                if out.exists() and out.stat().st_size == info.file_size:
                    print(f"  have {out.name}")
                    continue
                print(f"  extracting {out.name} ({info.file_size / 1e9:.2f} GB)")
                with zf.open(info) as src, open(out, "wb") as dst:
                    while chunk := src.read(1 << 22):
                        dst.write(chunk)


def convert(con: duckdb.DuckDBPyConnection) -> dict[str, dict]:
    counts: dict[str, dict] = {}
    for table in TABLES:
        shards = sorted(TSV.glob(f"{table}-*.tsv"))
        if not shards:
            raise SystemExit(f"no TSV shards found for {table}")
        out = INTERIM / f"{table}.parquet"
        files = "[" + ", ".join(f"'{p}'" for p in shards) + "]"
        # quote/escape disabled: the TSVs are not quoted and note text contains
        # bare double quotes that would otherwise swallow field boundaries.
        reader = (
            f"read_csv({files}, delim='\\t', header=true, quote='', escape='', "
            f"sample_size=-1, null_padding=true)"
        )
        con.execute(f"COPY (SELECT * FROM {reader}) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        n = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
        ncols = len(con.execute(f"SELECT * FROM read_parquet('{out}') LIMIT 0").description)
        counts[table] = {"rows": n, "columns": ncols, "parquet_bytes": out.stat().st_size}
        print(f"  {table}: {n:,} rows, {ncols} columns -> {out.name}")
    return counts


def main() -> None:
    snap = snapshot_dir(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"snapshot: {snap.name}")
    INTERIM.mkdir(parents=True, exist_ok=True)
    extract(snap)
    con = duckdb.connect()
    counts = convert(con)
    summary = {"snapshot": snap.name, "tables": counts}
    (INTERIM / "row_counts.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
