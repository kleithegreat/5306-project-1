# AGENTS.md

## What this project is

CS 5306 / INFO 5306 (Cornell, Fall 2026), Project 1. Team Katseye: Kevin Lei (kl2344),
Kyungmin Nam (kn467), Brittany Sun (bs835).

We are studying X's Community Notes, a crowdsourced fact-checking system where
contributors write notes on posts and other contributors rate them. Notes are published
only if a matrix-factorization scoring model finds approval from raters with differing
inferred viewpoints, so a note can end up rated Helpful, rated Not Helpful, or sit
unresolved in Needs More Ratings (NMR) indefinitely.

**Our question:** does the outcome of a contributor's first note predict whether they
keep contributing, and in particular, is explicit rejection associated with different
retention than getting no verdict at all?

The Not Helpful vs. NMR comparison is the point of the project. Helpful is a reference
point. Wikipedia research says negative early feedback predicts newcomer departure, but
Wikipedia has no clean analogue of "no verdict ever arrived", which is what makes this
system worth looking at.

## Read this next

**`PROGRESS.md` is the plan of record.** It holds the milestones, what each produces,
what counts as done, and where human review gates sit. Work the lowest-numbered
milestone whose dependencies are `DONE`. Update its status there when you finish, and
append what you did to `docs/worklog.md`.

Do not begin work past a `HUMAN GATE` that is not marked `PASSED`.

## Data

Public bulk downloads, <https://communitynotes.x.com/guide/en/under-the-hood/download-data>.
Three tables:

- `notes` — one row per note, sharded. Author ID, creation time, post ID, classification
  and reason tags, note text.
- `noteStatusHistory` — one row per note. `firstNonNMRStatus` and
  `timestampMillisOfFirstNonNMRStatus` are what the project rests on: the first real
  verdict and when it arrived. Empty means the note never left NMR.
- `userEnrollment` — small, used for the writing-lockout check.

We are deliberately not using the `ratings` table (tens of GB, and we need note outcomes
rather than individual ratings) or the text of the annotated posts (not public, requires
paid API access).

Upstream publishes daily and keeps roughly a week; older dates 404. Each snapshot is
cumulative back to 2021, so a single snapshot is enough — but once downloaded it is the
only copy, so **never modify or delete `data/raw/`**. The snapshot date lives in
`docs/worklog.md`, not in this file.

## House rules

- **Don't write down what can be queried.** Repo layout, row counts, file sizes, column
  lists: read them at runtime. Docs are for decisions and the reasons behind them, which
  are the part that cannot be recovered from the repo later.
- **Use DuckDB** over the Parquet files for anything touching the full tables. Do not
  load the raw tables into pandas.
- **Deterministic and rerunnable.** Seed anything random. A script should produce the
  same output twice.
- **Never claim causation.** We did not assign anyone to Not Helpful or NMR. Write
  "predicts" and "is associated with". A weak first note plausibly produces both a bad
  verdict and a contributor who was leaving anyway.
- **No hand-typed numbers.** The report and slide quote `out/results.json`.
- **Do not silently drop rows.** Exclusions are boolean columns with counts, applied in
  one place (`src/exclusions.py`), documented in `docs/exclusions.md`.
- **Log the mess.** `docs/worklog.md` records decisions, dead ends, and things that
  broke. The assignment explicitly asks what three people spent four weeks doing, so
  the failures are worth as much as the results.
- **Flag surprises rather than working around them.** An unexpected status value, an
  author ID mismatch, a check that fails: write it at the top of the relevant doc and
  stop, do not patch around it.
