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

---

## HUMAN GATE 2 passed — contributor table frozen (2026-09-18)

Kevin accepted `docs/validation.md`. **`data/processed/contributors.parquet` is frozen
as of commit `ca09296`.** Later milestones may filter it; rebuilding it needs a human to
say so.

He also delegated the remaining open call. Recorded here because it changes the sample:

**Authors whose first note has no `noteStatusHistory` row are excluded.** All 15,997 of
them. We do not know what happened to those notes, and the alternative — calling them NMR
— would put a group that grows from 3.1% of the 2024 cohort to 9.9% of 2026 into the
comparison group, manufacturing a cohort trend out of a data-coverage artefact. Excluding
them costs 4.7% of authors and is the conservative direction: it removes cases from the
NMR side, which is the side the headline result needs to be strongest.

---

## M0 follow-up — author IDs are stable (2026-09-18)

Done inside the download window after all. `src/check_id_stability.py` compares
`noteStatusHistory` across the 2026-09-18 and 2026-09-16 releases: **3,282,773 notes in
both, zero author-ID mismatches**, and nothing present in the older release had
disappeared from the newer one. The report can say we checked rather than assumed.

## M5 — Exclusions (2026-09-18)

`src/exclusions.py` is the only way anything downstream gets a sample. 343,176 authors →
**322,094**. AI writers cost 35, pre-2023 cohorts 5,052, unscored first notes 15,997.
`flag_not_misleading` is carried but not applied, per Gate 1.

## M6a–M6f, M7 — Analysis (2026-09-18)

**The headline is −15.0 pp** (30-day retention, Not Helpful minus NMR, 95% CI −15.5 to
−14.5). Helpful sits only +2.1 pp above NMR. The asymmetry is the first surprise:
approval barely moves anyone, rejection moves a lot.

**M6c found a structural break and it changes the finding.** The gap is −6.1 pp for
cohorts before 2024-04 and −17.1 pp from 2024-04 onward, and the monthly series shows Not
Helpful retention collapsing from ~28% in 2024-02 to 9.6% in 2024-04. That is the month X
began locking writing ability on a single Not Helpful note. 2024-03 is already part-way
there, which is what you would expect given verdicts arrive days after the note.

**M6f bounds it, and the bound is uncomfortable.** 89.4% of Not Helpful authors have
earned out at least once against 16.8% of NMR authors, and 48.7% are still locked out.
Among Not Helpful authors who wrote exactly one note and earned out, the median gap
between verdict and earn-out is **0.03 days** and 84% earned out within a week. The
verdict and the lockout are effectively the same event.

The obvious objection — that `timestampOfLastEarnOut` is the most recent earn-out, so a
2023 author's could have happened later under the new rule — turned out to matter. Only
**1.2%** of pre-2024-04 Not Helpful authors have an earn-out stamped before the rule date,
against 0.3% of NMR. So the pre-rule cohorts really were unlocked, and their −6.1 pp gap
is not mechanical. At most 1.2 of those 6.1 points could be.

**So the honest finding is not the one we set out expecting.** An explicit Not Helpful
verdict predicts sharply lower continued contribution than no verdict — but most of that
is X's lockout doing what it was built to do, not contributors giving up. The
discouragement association is the ~5 points visible before the lockout rule existed, not
the 15 points in the pooled sample. `docs/lockout.md` says this in full. **The headline
sentence needs a human decision at Gate 3**, because the natural phrasing of M6a's number
would be misleading on its own.

Smaller things worth keeping:

- **M6b:** the naive specification gives −21.1 pp against the landmark's −15.0, overstating
  by 6.1 pp. Most of that is keeping the authors who wrote again within the week, before
  any feedback could have reached them. Censoring was held identical in both so the
  comparison isolates the landmark.
- **M6d:** Kaplan-Meier agrees with the landmark proportions to within half a point at day
  90 (43.7 / 19.0 / 41.2 against 43.7 / 19.3 / 41.4), which is a useful independent check
  on the censoring. `lifelines` never built (see M0), so this is `statsmodels`.
- **M6e:** the regression gives −18.5 pp against the raw −15.0. Not a contradiction —
  cohort fixed effects make the comparison within cohort, which drops the early cohorts'
  smaller gaps out of the average. Both numbers are reported. A first note saying the post
  is *not* misleading is associated with **+2.5 pp** retention once status is held
  constant, which supports the Gate 1 decision to keep those notes in.
- **M7:** every variation keeps the sign, spanning −5.7 to −18.2 pp against the −15.0
  baseline. The stricter "two or more later notes" definition is the low end, k=3 the high
  end. None of this is where the sensitivity lives; M6c is.

## M8 — Figures (2026-09-18)

Four vector PDFs generated from `out/tables/` only. Palette is Okabe-Ito blue /
vermillion / bluish-green, checked with a colourblind-separation validator rather than by
eye — the first choice used grey for NMR and failed a chroma floor.

Drawing fig3 exposed a real artefact. The most recent cohort month spiked upward in every
series, because only authors who joined in the first days of that month could have a
30-day window close before the data cutoff — a biased slice, not a cohort. Fixed in the
analysis rather than the chart: `by_cohort.csv` now carries `cohort_complete`, the
markdown flags partial months, and fig1 and fig3 drop them.

## M9 — Numbers freeze (2026-09-18)

`out/results.json` is built by `src/collect_results.py` from `out/tables/` and nothing
else. Two numbers were hand-typed into it on the first pass and have been replaced by
values read from `lockout_summary.csv`. The report and slide quote this file only.
