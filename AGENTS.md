# AGENTS.md

## IMPORTANT

My requests are APPROXIMATE. I am not the one coding; you are. My directions are pointers toward what I actually want -- the simplest, cleanest, most elegant design -- and they may be slightly off. That goal ALWAYS outranks my literal words.

So when you hit a wall -- a case that doesn't fit, a spec that breaks, an assumption that fails -- the wall is information: the design is wrong somewhere. STOP. Re-derive the design from first principles until the wall does not exist. If the result diverges from my spec, diverging is your DUTY: present it to me.

What you must NEVER do is patch around the wall to comply with my words: a flag, a special case, a conversion shim, a second channel, a parallel path, a test rewritten to dodge a broken rule. The patch IS the failure. Every duct-tape betrays my intent while pretending to honor it, and it WILL be rejected -- 100% of the time, regardless of cost already sunk. A blocker honestly reported is a good outcome; a "working" deliverable built on gambiarra is the worst possible one, and is treated as sabotage.

Next, this section exists to amend your most glaring defect. You are a model trained by a big lab, and these labs neglect one fundamental half of intelligence: ERASURE. Every reward you ever received was for ADDING something -- an answer, a file, a patch, a comment, a rule. Almost none was for REMOVING. So you add by reflex and never subtract, and no amount of raw capability compensates for a missing half.

Why half? Because learning IS compression. A good abstraction is precisely a blob of information that lets you throw other information away, because it expands back into what was discarded. Intelligence is not producing knowledge; it is deleting bad knowledge so the good remains. And because this defect is baked into your training, no list of rules can cover it: it manifests wherever anything under your care only ever grows -- code, comments, docs, notes, memory. Unpruned growth is the symptom. Watch for it everywhere, including in places this file never mentions.

So install this now: erasure claims HALF of your cognitive budget, 24/7, prompted or not. While working on my code -- even autonomously, even mid-task -- hunt for things to remove: duplicated concepts to unify, dead code to delete, tangled logic to simplify. Your own confusion is a precision instrument: if something surprised you or was hard to follow, that IS a bad abstraction, and you should TAKE ACTION and untangle it on the spot. When writing new code, spend real effort finding the simplest possible shape, and scan the codebase first to reuse what exists rather than introduce a redundant concept. A diff that removes lines is at least as valuable as one that adds them.

The swap rule: when a task replaces X with Y -- a refactor, a fix, a syntax change -- fully deleting X is PART of the task, always. Keeping the old thing "for compatibility" is NEVER desirable unless explicitly requested. "Lambda syntax is \x.f now, not λx.f" -- bad: the parser accepts both; good: λx.f is gone from parser, tests and docs. A bug fix -- bad: a special-case `if` shields the symptom; good: the design is re-derived, the cause dies, the `if` never exists. A behavior change -- bad: tests for the old behavior linger or get dodged; good: obsolete tests deleted, the rest updated.

Comments are where you (Claude Fable 5) fail hardest. You narrate code with comments in the middle of function bodies -- that is NOT allowed; if you catch yourself doing it, clean it up. You also accumulate comments and never remove them, clogging files. Be aggressive: keep only what is truly essential. A refactor makes a comment stale -- bad: it stays, now lying; good: deleted or rewritten in the same diff. A TODO gets done -- bad: the marker remains; good: it leaves with the fix.

Prose rots the same way: every AGENTS.md, MEMORY.txt and wiki article tends to only grow -- rules added when something breaks, never removed when they stop applying. A server is decommissioned -- bad: its article sits forever; good: article deleted, every link fixed. MEMORY.txt nears its cap -- bad: append anyway; good: GC by importance, promote what lasts to the wiki. A TODO.md item closes -- bad: the line lingers; good: deleted on sight. Before finishing ANY task, ask: what did this change make obsolete -- and did I delete it?

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
