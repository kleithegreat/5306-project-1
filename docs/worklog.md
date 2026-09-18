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

---

## M2 — Schema and data dictionary (2026-09-18)

`src/profile_schema.py` generates `docs/data-dictionary.md` entirely from the Parquet
files. Nothing in it is hand-typed and nothing is copied from X's published column
descriptions, so it records what this snapshot contains rather than what it should.

**The surprise: 233,514 notes — 7.6% — have no `noteStatusHistory` row at all.** The
published description implies that table covers every scored note, and it does not. These
notes have no recorded outcome of any kind, which is *not* the same as never leaving NMR,
and folding the two together would inflate the NMR group.

It is not a recency artefact. The affected notes run from 2024-03-19 to the end of the
snapshot, across 28 months, at a rate rising from 6.7% in 2025-12 to 14.1% in 2026-09.
No single cause is visible in the data: the rate is 10.7% for misleading notes and 4.5%
for not-misleading, 9.7% for non-media and 6.2% for media, 9.3% for regular notes and
22.7% for collaborative ones. Collaborative notes are the worst affected but are far too
few to explain the total.

**15,997 authors (4.7%) have an unscored first note** — 3.1% of the 2024 cohort, 7.7% of
2025, 9.9% of 2026. Because the rate trends upward over time, treating these as NMR would
bias the cohort analysis in M6c in a direction that looks like a real trend. Flagged, not
worked around; the disposition is Gate 2's and M5's call. See M3 below for how the table
represents it.

Other things the profile turned up, none of which change the plan:

- The author identifier is `noteAuthorParticipantId` in both `notes` and
  `noteStatusHistory`, and `participantId` in `userEnrollment`. The published dictionary
  calls the `notes` column `participantId`, which is wrong for this snapshot. The two
  note tables never disagree about a note's author (0 conflicts on 2.85M joined notes),
  and every one of the 343,176 note authors has a `userEnrollment` row.
- `believable`, `harmful` and `validationDifficulty` are 99.2% null — the fields
  deprecated in 2022-10.
- `timestampMinuteOfFinalScoringOutput` has exactly one distinct value across 3.29M rows.
- `timestampMillisOfRetroLock` is 100% null, so the January 2023 retro-lock left no trace
  in this snapshot.

## M3 — Contributor table (2026-09-18)

`src/build_contributors.py` writes `data/processed/contributors.parquet`: 343,176 rows,
one per distinct note author, matching the note table exactly. Nothing is filtered.

First note is earliest `createdAtMillis`, ties broken by `noteId` so the ordering is
total and the build is deterministic. The second note comes from `lead()` over the same
window rather than a self-join. Reason-tag columns are discovered from the schema rather
than hardcoded, and stored as a list of the tags the author actually set.

**Two columns beyond the M3 spec, both because the spec conflated things the data
separates.**

`first_note_scored` — whether the first note has a `noteStatusHistory` row at all. The
spec says `first_verdict_status` is "null if never resolved", but after M2 null means
either "sat in NMR and never resolved" or "we have no outcome record for this note".
Those are different facts and the second one trends over time. Rather than pick one
meaning, the table carries both: `first_verdict_status` exactly as specified, and a
boolean saying whether the lookup found anything. M5 decides what to do with it.

`data_cutoff_at` — the latest note creation time in the snapshot (2026-09-16), alongside
`snapshot_at` (2026-09-18) as specified. Snapshots only contain notes created up to 48
hours before release, so censoring against `snapshot_at` would credit two days of
observation that cannot contain a note. **M6a must censor against `data_cutoff_at`.**

## M4 — Validation (2026-09-18)

`src/validate_contributors.py` writes `docs/validation.md`. **12 of 12 checks pass and
all 20 hand-checked authors match the raw TSVs field for field.**

The hand-check rebuilds each sampled author from the TSVs in plain Python — separate
parser, separate code path, no DuckDB — so a bug shared between the build query and the
checks cannot hide in both. Authors are sampled by `md5(author_id || seed)`, so the same
20 come back on every run.

Two checks were added beyond the six the milestone lists. Comparing TSV newline counts
against Parquet row counts confirms the conversion did not merge or split rows, which is
the failure mode the `quote=''` setting exists to prevent — note text contains bare double
quotes, and it turns out no note text contains a raw newline. Comparing
`epoch_ms(raw_millis)` against each stored timestamp confirms the UTC conversion, which
is why M3 keeps the raw millis columns.

Nothing needed investigating: no author has a second note before their first, no first
verdict precedes the note it belongs to, and `first_verdict_at` is null exactly when
`first_verdict_status` is.

The timing table in `docs/validation.md` restates, now at author level, why the day-7
landmark is the right choice and why the early cohorts were dropped at Gate 1: from 2023
the median first note waits 0.23–0.34 days for a verdict and the 90th percentile is
1.4–4.2 days, while the 2021 cohort has 2,938 authors and not one recorded verdict.
