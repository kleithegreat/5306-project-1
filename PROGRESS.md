# PROGRESS.md

Plan of record for Project 1. Read `AGENTS.md` first for the question, the data, and the
house rules; this file is only the sequence of work.

Milestones form a DAG: start one when every milestone in its `Depends on` line is `DONE`.
Status values are `TODO`, `IN PROGRESS`, `BLOCKED`, `DONE`. A `HUMAN GATE` blocks
everything downstream of it until a human marks it `PASSED`.

---

## M0 — Snapshot and conversion

**Status:** DONE
**Depends on:** nothing

Download the current `notes`, `noteStatusHistory`, and `userEnrollment` into `data/raw/`.
Record the snapshot date in `docs/worklog.md`. Upstream drops snapshots after about a
week, so from that moment this is the only copy and nothing may overwrite it.

Convert to Parquet under `data/interim/`, leaving the TSVs untouched. Log row counts per
table in the worklog. There is no published expectation to check them against, so the
counts recorded here are the baseline every later milestone validates against.

Worth doing while the window is open, and only then: download a second snapshot a few
days later and check that author identifiers for a sample of notes match across the two.
The analysis assumes author IDs are stable across releases. If nobody gets to it, the
report says we assumed it — it does not say we checked.

**Done when:** the three tables are in `data/raw/`, Parquet copies exist, and the
snapshot date and row counts are in `docs/worklog.md`.

---

## M1 — System rules research

**Status:** DONE
**Depends on:** M0
**Output:** `docs/system-rules.md`

Three questions that could change how the results are interpreted. Answer each from the
official Community Notes documentation and source, citing URLs.

1. **Writing lockouts.** Can Not Helpful ratings cost a contributor the ability to write
   notes? Find the current Writing Impact rules, the thresholds involved, and whether a
   single Not Helpful first note can trigger `atRisk` or a lockout. This is the biggest
   threat to the headline result: if rejection mechanically blocks writing, a retention
   gap is the system locking people out rather than people giving up.
2. **Rater gating.** Contributors must earn rating impact before they may write. Record
   the current requirement and when it was introduced. This means our "newcomers" are
   experienced raters, which must be stated in the report.
3. **AI note writers.** X added AI note-writer accounts in 2025. Determine whether they
   are identifiable in the public tables (a column, a flag, an enrollment state) or not
   identifiable at all. If not identifiable, say so plainly; do not invent a heuristic
   without flagging it as one.

Also record the algorithm and policy changes with dates that plausibly affect note
outcomes, for the cohort discussion in M6c.

**Done when:** all three are answered with sources, and the places where the
documentation is ambiguous are called out as ambiguous.

---

## HUMAN GATE 1

**Status:** PASSED (2026-09-18, Kevin Lei — decisions at the bottom of `docs/system-rules.md`)

A human reads `docs/system-rules.md` and decides:

- whether the lockout rule needs a dedicated report section, a paragraph, or a footnote
- whether AI authors will be excluded, and by what rule
- whether any cohorts should be dropped entirely

Write the decisions at the bottom of `docs/system-rules.md` under `## Decisions`, then
mark this gate `PASSED`.

---

## M2 — Schema and data dictionary

**Status:** DONE
**Depends on:** M0
**Output:** `docs/data-dictionary.md`

Inspect the columns actually present in this snapshot rather than assuming. For each
column in the three tables: name, type, null rate, and for categorical columns the
distinct values with counts.

Pay attention to:

- the author identifier column name in each table, and whether the two agree
- `createdAtMillis`, `timestampMillisOfFirstNonNMRStatus`, `firstNonNMRStatus`
- the full set of status values actually observed, not the ones we expect
- `classification` values and the reason-tag columns
- any column that distinguishes note source or author type

**Done when:** the dictionary is written and any surprise (unexpected status value, high
null rate in a key field, author ID mismatch between tables) is flagged at the top.

---

## M3 — Contributor table ETL

**Status:** DONE
**Depends on:** M2
**Output:** `data/processed/contributors.parquet`, `src/build_contributors.py`

Join `notes` to `noteStatusHistory` on note ID. Group by author, order notes by
`createdAtMillis`, and emit one row per author:

| field | meaning |
| --- | --- |
| `author_id` | stable participant identifier |
| `first_note_id` | |
| `first_note_at` | timestamp, UTC |
| `cohort_month` | `YYYY-MM` of `first_note_at` |
| `first_verdict_status` | `firstNonNMRStatus`, null if never resolved |
| `first_verdict_at` | `timestampMillisOfFirstNonNMRStatus`, null if never resolved |
| `second_note_at` | timestamp of the author's next note, null if none |
| `n_notes_total` | count of notes by this author in the snapshot |
| `first_classification` | e.g. misleading / not misleading |
| `first_has_url` | bool, source cited in note text |
| `first_note_len` | characters |
| `first_reason_tags` | the author's reason tags, as a list or bitmask |
| `snapshot_at` | snapshot date, identical on every row |

Rules:

- All timestamps in UTC. Store as timestamps, not raw millis, but keep the raw millis
  columns too so validation can check the conversion.
- An author's "first note" is their earliest note in this snapshot. Since each snapshot
  is cumulative back to 2021, that is their true first note.
- Do not filter anything here. Exclusions happen in M5 so they stay visible and
  reversible.

**Done when:** the Parquet file exists, the script is deterministic and rerunnable, and
the row count equals the number of distinct authors in `notes`.

---

## M4 — Table validation

**Status:** DONE
**Depends on:** M3
**Output:** `docs/validation.md`, `src/validate_contributors.py`

1. Distinct author count in `contributors.parquet` equals distinct author count in `notes`.
2. Sum of `n_notes_total` equals total note count.
3. No author has `second_note_at` earlier than `first_note_at`.
4. `first_verdict_at` is null exactly when `first_verdict_status` is null.
5. Rows where `first_verdict_at` precedes `first_note_at` — should be zero; if not,
   investigate before proceeding, do not silently drop them.
6. Distribution of time from note creation to first verdict (median, p90, share never
   resolved). Sanity: most resolutions happen within days, not months.
7. Hand-check: sample 20 authors at random, pull their raw rows from the TSVs, and
   verify every field by hand. Write the 20 cases into `docs/validation.md` in full.

**Done when:** all checks pass, or failures are documented with an explanation.

---

## HUMAN GATE 2

**Status:** PASSED (2026-09-18, Kevin Lei — `docs/validation.md` accepted; table frozen)

A human reads `docs/validation.md`, in particular the 20 hand-checked authors, and
confirms the table is trustworthy. After this gate the contributor table is **frozen**:
later milestones may filter it but may not rebuild it without a human saying so.

Mark `PASSED` and note the freeze in `docs/worklog.md`.

---

## M5 — Exclusions layer

**Status:** DONE
**Depends on:** HUMAN GATE 1, HUMAN GATE 2
**Output:** `src/exclusions.py`, `docs/exclusions.md`

Implement the exclusions decided at Gate 1 as a function applied on top of the frozen
table, with one boolean column per exclusion reason rather than deleted rows. Report how
many authors each exclusion removes, overall and by cohort.

Expected exclusions: AI note-writer accounts (if identifiable), and any cohort a human
ruled out. Optional flag, used only in M7: notes classified not misleading.

**Done when:** every downstream analysis gets its sample from this one function, and
`docs/exclusions.md` gives the counts.

---

## M6a — Primary analysis: day-7 landmark

**Status:** DONE
**Depends on:** M5
**Output:** `out/tables/primary.csv`, `out/tables/primary.md`, `src/analysis_primary.py`

This is the headline result. Everything else supports it.

For landmark `k = 7` days:

1. Drop authors whose `second_note_at` falls before `first_note_at + k`. They returned
   before any feedback could have reached them.
2. Drop authors whose `first_note_at + k` is after `snapshot_at`. Not yet observable.
3. Classify the first note by its status **as of day k**: Helpful if
   `first_verdict_status` is Helpful and `first_verdict_at <= first_note_at + k`, Not
   Helpful likewise, still NMR otherwise. A note resolved after day k is `NMR` here, by
   design.
4. Retention: did the author write another note in days `k+1` through `k+30`? Repeat for
   60 and 90. Drop authors whose window extends past `snapshot_at` (censored).
5. For each status and window: n, number retained, proportion, Wilson 95% interval.
6. Compute the Not Helpful minus NMR difference with a 95% interval (Newcombe or
   bootstrap; state which). Also Helpful minus NMR.

Report sample sizes at every step so the reader can see what each filter costs.

**Done when:** the table exists and `primary.md` opens with a one-sentence statement of
the result.

---

## M6b — Naive comparison

**Status:** DONE
**Depends on:** M5
**Output:** `out/tables/naive.csv`, `out/tables/naive.md`

The same retention numbers computed the obvious way: classify the first note by its
eventual `firstNonNMRStatus` whenever that arrived (null = NMR), measure retention in the
30/60/90 days after the first note, no landmark, no pre-landmark drop.

Then quantify the gap: how much does the Not Helpful minus NMR difference move against
M6a, and in which direction? Also report, for the naive NMR group, the distribution of
first-note dates, to show that it skews recent.

The difference between the two specifications is itself a reportable finding about how
easy it is to get this question wrong.

**Done when:** the table exists and the comparison to M6a is written up in `naive.md`.

---

## M6c — Cohort breakdown

**Status:** DONE
**Depends on:** M5
**Output:** `out/tables/by_cohort.csv`, `out/tables/by_cohort.md`

Repeat the M6a day-7 analysis separately by `cohort_month`. Report 30-day retention by
status per cohort with intervals, plus n per cell. Suppress or flag cells with fewer than
50 authors rather than plotting noise.

Cross-reference the policy and algorithm change dates from `docs/system-rules.md`, and
note whether any visible shift lines up with one.

**Done when:** the table exists and cells too small to interpret are marked.

---

## M6d — Survival curves

**Status:** DONE
**Depends on:** M5
**Output:** `out/tables/km.csv`, `src/analysis_survival.py`

Kaplan-Meier estimate of time from day k to the author's next note, stratified by day-7
status. Event is the second note. Censoring time is `snapshot_at` minus
`first_note_at + k`. State the censoring rule explicitly in the output.

Report the curves out to 90 days with confidence bands, plus median time to return per
group where it is reached. Optionally a log-rank test between Not Helpful and NMR.

Do not produce a plain "fraction returned by day t" curve. Without censoring handled,
later cohorts drag it downward for reasons unrelated to the question.

**Done when:** the curve data is written as a table M8 can plot directly.

---

## M6e — Logit regression

**Status:** DONE
**Depends on:** M6a
**Output:** `out/tables/logit.csv`

Logistic regression of 30-day retention on day-7 status, NMR as the reference category,
with `cohort_month` fixed effects and the first-note features from M3 as controls
(classification, has URL, length, reason tags).

Report coefficients as odds ratios with intervals, and as marginal effects in percentage
points so the report can state them in the same units as M6a.

Supporting evidence only. If the regression and the raw proportions disagree, say so
rather than picking the more convenient one.

**Done when:** the table exists and its direction and rough size agree with M6a, or the
disagreement is documented.

---

## M6f — Lockout check

**Status:** DONE
**Depends on:** M5
**Output:** `out/tables/enrollment.csv`, `docs/lockout.md`

Using `userEnrollment` and the rules from M1, estimate how much of any Not Helpful
retention deficit could be mechanical rather than motivational.

- Distribution of enrollment states among authors in each day-7 status group.
- Share of Not Helpful authors in a state consistent with having lost writing ability.
- If enrollment timestamps allow it, whether state changes cluster after a first Not
  Helpful verdict.

`userEnrollment` gives current state only, not history, so this bounds the problem rather
than solving it. Say that in the writeup.

**Done when:** `docs/lockout.md` states what the data can and cannot rule out.

---

## M7 — Robustness

**Status:** DONE
**Depends on:** M6a
**Output:** `out/tables/robustness.csv`

Rerun M6a under each variation and tabulate the Not Helpful minus NMR difference:

- landmark `k` = 3, 7, 14 days
- excluding notes classified not misleading
- retention defined as two or more later notes instead of one
- restricted to cohorts with at least 90 days of post-window observation

One row per variation.

**Done when:** the table exists and any sign flip or large swing is flagged for the
report.

---

## M8 — Figures

**Status:** DONE
**Depends on:** M6a, M6b, M6c, M6d
**Output:** `out/figures/`, `src/figures.py`

Four figures, generated from the tables in `out/tables/`, never from a re-run of the
analysis. Vector PDF, colourblind-safe palette, consistent colours for Helpful / Not
Helpful / NMR across all figures, legible at print size.

1. **fig1** — newcomers per month, stacked by first-note day-7 outcome. Context.
2. **fig2** — retention by outcome at 30/60/90 days, points with confidence intervals. **Core.**
3. **fig3** — 30-day retention by cohort month, three lines, intervals as bands. **Core.**
4. **fig4** — Kaplan-Meier curves by outcome with confidence bands.

If time runs short, fig2 and fig3 are the ones that must exist.

**Done when:** all figures render and each has a one-line caption draft in
`out/figures/captions.md`.

---

## M9 — Numbers freeze

**Status:** DONE
**Depends on:** M6a–M6f, M7, M8
**Output:** `out/results.json`

Collect every number that will appear in the report or slide into one JSON file: sample
sizes, retention proportions and intervals, the headline difference, cohort highlights,
regression marginal effects, robustness range, exclusion counts.

After this, the report and slide quote `out/results.json` and nothing else.

**Done when:** the file exists and every figure's underlying numbers are traceable to it.

---

## HUMAN GATE 3

**Status:** PASSED (2026-09-18, Kevin Lei — headline chosen; see `out/results.json` `headline.statement`)

A human reviews `out/results.json`, the four figures, and the one-sentence headline. This
is the main review point: everything after it is writing.

Decide: is the headline sentence the one we want, does anything look implausible, and
does the lockout caveat get a section or a paragraph? Mark `PASSED`.

---

## M10 — Report

**Status:** DONE
**Depends on:** HUMAN GATE 3
**Output:** `paper/report.pdf`

Fill in `paper/report.tex`. Required content, per the assignment: what we asked, how we
answered it, what the answer was, and what three people actually spent four weeks doing.

Writing rules:

- "predicts", "is associated with". Never "causes" or "effect".
- Every number comes from `out/results.json`.
- The technical-work section draws on `docs/worklog.md`, including what did not work.
- State plainly that contributors must earn rating impact before writing, so our
  newcomers are experienced raters.

**Done when:** it compiles, is within a sensible length, and a human has edited the prose.

---

## M11 — Slide

**Status:** TODO
**Depends on:** HUMAN GATE 3
**Owner:** human
**Output:** a one-slide `.pptx`

Built directly in PowerPoint. The LaTeX/beamer route was tried and dropped — for a single
slide it cost more layout fighting than it saved, and Canvas wants pptx anyway.

Content: the question in one line, `out/figures/fig3_cohorts.pdf` (the cohort figure —
the April 2024 break is visible without narration), the answer in one sentence, and the
three names and NetIDs. No numbers on it that cannot be said aloud in sixty seconds.

Suggested wording, from `out/results.json`: rejected authors are 15 points less likely to
write again within 30 days, but since April 2024 a single Not Helpful note revokes writing
ability and 89% of rejected first-timers lose it, usually the same day; before that rule
the gap was about 5 points.

**Done when:** a pptx exists and someone has read it aloud with a timer.

---

## M12 — Final review and submit

**Status:** TODO
**Depends on:** M10, M11
**Owner:** human

Slide due **Sunday October 4, 10:00pm**. Report due **Monday October 5, 10:00am**, so
finish the report Sunday night.

Checklist: both files are PDF and PPTX as required, all three names and NetIDs appear,
figures are legible in print, every claim in the report traces to `out/results.json`, and
no sentence claims causation.

---

## Suggested schedule

| Dates | Milestones |
| --- | --- |
| Sep 18–21 | M0, M1, M2, M3, M4, Gates 1 and 2 |
| Sep 22–27 | M5, M6a–M6f |
| Sep 28–Oct 2 | M7, M8, M9, Gate 3 |
| Oct 3–4 | M10, M11 |
| Oct 4 evening | M12, submit slide by 10pm |
| Oct 5 | submit report by 10am |
