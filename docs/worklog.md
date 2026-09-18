# Worklog

Decisions, dead ends, and things that broke. Newest milestone last.

---

## M0 — Snapshot and conversion (2026-09-18)

**Snapshot date: 2026-09-18.** This is the only copy. Upstream keeps roughly a week.

Downloaded from `https://ton.twimg.com/birdwatch-public-data/2026/09/18/`. Shard counts
were probed rather than assumed: `notes` has 5 shards, `noteStatusHistory` and
`userEnrollment` one each. Shard 0 of `notes` holds 98.4% of the rows; shards 1–4 are
~12k rows each. Shard 5 onward 404s.

### Baseline row counts

Every later milestone validates against these.

| Table | Rows | Columns |
| --- | ---: | ---: |
| `notes` | 3,086,867 | 24 |
| `noteStatusHistory` | 3,290,294 | 23 |
| `userEnrollment` | 1,490,672 | 8 |

Derived facts worth having on hand: 343,176 distinct note authors; notes created
2021-01-28 through 2026-09-16.

`noteStatusHistory` carries 203,427 more rows than `notes`. This is expected, not a
defect: the download-data page states that deleted notes disappear from `notes` but their
status history is retained. It does mean the two tables answer different questions, and
that our author population is drawn from surviving notes only — a survivorship issue the
report should mention.

The last note in the snapshot is dated 2026-09-16, two days before the snapshot. The
docs say snapshots contain only notes created as of 48 hours before release. **Censoring
in M6a should use 2026-09-16, not the snapshot date**, or it will count two days of
guaranteed-empty observation as real.

### Layout decision

`data/raw/2026-09-18/` holds the downloaded `.zip` files exactly as retrieved and is
never written to again. TSVs are extracted to `data/interim/tsv/` and Parquet written to
`data/interim/`. The alternative — extracting into `data/raw/` — would have meant writing
into the directory we promised never to touch. The TSVs are kept rather than converted
and discarded because M4's hand-check pulls raw rows from them.

`src/convert_snapshot.py` is rerunnable: extraction is skipped when the TSV already
exists at the size the zip advertises, and Parquet is rewritten each run. Counts land in
`data/interim/row_counts.json`.

DuckDB's CSV reader is called with `quote=''` and `escape=''`. Note text contains bare
double quotes, and with default quoting they swallow field boundaries and silently
corrupt row counts.

### Second-snapshot author-ID check: not done

M0 suggests downloading a second snapshot a few days later to confirm author IDs are
stable across releases. Not done yet, and it can only be done while the window is open
(by roughly 2026-09-25). **The report must say we assumed ID stability, not that we
checked it**, unless someone does this.

### Environment

`flake.nix` pins nixpkgs and provides Python with duckdb, pyarrow, pandas, numpy, scipy,
statsmodels and matplotlib. Enter with `nix develop`.

Dead end: `uv venv` first, which fails on NixOS — uv's downloaded CPython is dynamically
linked against a generic-Linux loader that does not exist here.

Dead end: `lifelines` was in the flake for M6d survival curves and does not build in the
pinned nixpkgs — it requires `pandas<3.0` and nixpkgs ships 3.0.4. Dropped.
`statsmodels.duration.survfunc` provides `SurvfuncRight` and `survdiff`, which cover
Kaplan-Meier with confidence bands and the log-rank test. No shim, no pin override.

---

## M1 — System rules research (2026-09-18)

Output in `docs/system-rules.md`, with five flags at the top. Two of them change the
plan and are summarised here.

**The lockout threat is real but dated.** A single Not Helpful first note does lock a
newcomer's writing ability — but only under a rule added 2024-04-02. Before that a
newcomer needed 3 Not Helpful out of their last 5 resolved notes, and a first Not Helpful
note had no mechanical consequence at all. That date is a usable natural break rather
than a caveat we can only apologise for, and M6c should be built around it.

**The 2021 and 2022 cohorts are unusable.** `firstNonNMRStatus` is empty for every note
created before 2022-05 — not sparse, empty — so those cohorts are 100% NMR by
construction. The field only becomes reliably populated from 2023. Stopped and flagged
rather than filtering around it; the cohort decision is Gate 1's to make.

Also confirmed empirically while answering these questions, which saves M4 some work:
`timestampMillisOfFirstNonNMRStatus` is null exactly when `firstNonNMRStatus` is null
with no `0`/`-1` sentinels, no note has a verdict timestamp before its creation
timestamp, and from 2023 onward the median verdict lag is 0.24–0.35 days with p90 of
1.5–3.7 days. The last of these is the strongest evidence yet that a 7-day landmark is
the right choice: nearly every verdict that will ever arrive has arrived by then.

### Sources that would not fetch

The rendered guide at `communitynotes.x.com` is client-side rendered and returns an empty
shell to any plain HTTP fetch. The pages are built from markdown in
`github.com/twitter/communitynotes/documentation/`, which is what `system-rules.md`
cites. X's product blog returns 403, so one date (the September 2022 rater gate) rests on
trade coverage rather than the primary source; it is flagged as such in the doc and does
not touch the analysis.
