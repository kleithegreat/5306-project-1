# System rules (M1)

How Community Notes' own mechanics could produce or distort the retention gap we are
looking for. Everything below is from the official guide, the open-source scoring code,
or counts run against the snapshot in `data/interim/`.

Sources are cited inline. The guide's rendered pages are client-side rendered and do not
survive a plain fetch, so the citations point at the markdown sources in
`github.com/twitter/communitynotes`, which is what those pages are built from.

---

## Flags

Five things that change how the results must be read. Each is expanded below.

1. **A single Not Helpful first note can lock writing ability — but only since
   2024-04-02.** Before that date a newcomer needed 3 Not Helpful notes out of their last
   5 resolved. This is the headline threat, and the date split is the lever we have
   against it.
2. **`firstNonNMRStatus` is empty for every note created before 2022-05.** The
   2021-01 through 2022-04 cohorts are 100% NMR by construction, not by outcome. They
   cannot be used for the Not Helpful vs NMR comparison at all.
3. **AI note writers are identifiable**, via `userEnrollment.enrollmentState =
   'apiEarnedIn'`. 37 such accounts, 35 of which wrote notes: 265,605 notes, 8.6% of the
   snapshot, all since 2025-09-02. Identification is by *current* state only.
4. **Notes classified `NOT_MISLEADING` are structurally barred from Helpful.** Since
   2023 they are 583,444 notes, of which 164 (0.03%) ever reached Helpful, against 57,777
   (9.9%) Not Helpful. Comparable misleading notes: 15.1% Helpful, 4.4% Not Helpful. A
   first note of this kind can essentially only go NMR or Not Helpful.
5. **The data dictionary is incomplete on enrollment states.** `removed` (27,873
   accounts) appears in the snapshot but not in the published column description; the
   scoring code additionally defines `apiEarnedOut`, `apiTestUser` and
   `earnedOutNoAcknowledge`, none present here. Detail belongs in M2.

---

## 1. Writing lockouts

**Yes. Since 2024-04-02 a single Not Helpful first note is sufficient to lock a
newcomer's writing ability.**

The current rule ([`contributing/writing-ability.md`](https://github.com/twitter/communitynotes/blob/main/documentation/contributing/writing-ability.md),
rendered at <https://communitynotes.x.com/guide/en/contributing/writing-ability>):

> A contributor's ability to write new notes is temporarily locked if either (a) 3 or
> more of these 5 most recent notes have reached the status of Not Helpful, or (b) the
> contributor has a 0 or negative Writing Impact score, and a note reaches the status of
> Not Helpful.

Only notes that have reached Helpful or Not Helpful are counted; NMR notes are ignored.

Clause (b) is what bites. Writing Impact starts at 0 and only moves when a note resolves
([`contributing/writing-and-rating-impact.md`](https://github.com/twitter/communitynotes/blob/main/documentation/contributing/writing-and-rating-impact.md)).
A contributor whose first note reaches Not Helpful therefore satisfies (b) at that
moment, and is locked out. A contributor whose first note sits in NMR has Writing Impact
0 but no triggering verdict, and is not. This is exactly the contrast the project
measures, and the system itself acts on it.

The scoring code confirms the mechanism. `single_trigger_earn_out` in
[`scoring/src/scoring/contributor_state.py`](https://github.com/twitter/communitynotes/blob/main/scoring/src/scoring/contributor_state.py)
earns a contributor out when their counted Not Helpful notes exceed their counted Helpful
notes, they have a Not Helpful note since their last earn-out, and their state is not
`newUser`, `removed`, or already earned out. One Not Helpful and zero Helpful satisfies
`1 > 0`. A first-note author is in state `earnedIn`, not `newUser`, so nothing exempts
them.

Related constants in
[`constants.py`](https://github.com/twitter/communitynotes/blob/main/scoring/src/scoring/constants.py):
`isAtRiskCRNHCount = 2` (2 of the last 5 resolved notes Not Helpful puts a contributor in
`atRisk`; more than 2 earns them out), `maxHistoryEarnOut = 5`, `ratingImpactForEarnIn = 5`.

**The date matters more than the rule.** Clause (b) was added in commit
[`25b4ed57`](https://github.com/twitter/communitynotes/commit/25b4ed57), dated
**2024-04-02**, titled "Updated thresholds for writing lock/unlock". Before it the doc
read simply "If 3 or more of these 5 most recent notes have reached the status of Not
Helpful, the contributor's ability to write new notes is temporarily locked." Under the
old rule a first Not Helpful note had no mechanical consequence whatsoever.

That gives us a natural break. If the Not Helpful retention deficit is present in cohorts
before 2024-04 at a similar size to cohorts after, the deficit is not merely the system
locking people out. M6c should report cohorts either side of this date, and the report
should lean on that comparison rather than on argument.

Unlocking is not permanent exile: a locked contributor regains writing ability by
raising their Rating Impact by 5 the first time, and by a further 5 for each subsequent
lock. So a lockout suppresses note-writing for as long as it takes to earn that back,
which is unobservable to us.

**Ambiguity.** The public repo defines `single_trigger_earn_out` but does not contain the
job that calls it, so the exact counting window — whether "counted notes" means the last
5 resolved notes, notes since the last earn-out, or all notes — is not pinned down by
anything published. `maxHistoryEarnOut = 5` and the `lastNNotes` / `sinceLastEarnOut`
parameters of `_get_visible_note_counts` show the intended shape. For a contributor with
exactly one resolved note every reading gives the same answer, so this ambiguity does not
affect the first-note case.

## 2. Rater gating

**Confirmed: everyone in our data cleared a rating bar before they could write.**

New contributors can only rate. They unlock writing by reaching a Rating Impact of 5
([`contributing/writing-ability.md`](https://github.com/twitter/communitynotes/blob/main/documentation/contributing/writing-ability.md),
[`contributing/getting-started.md`](https://github.com/twitter/communitynotes/blob/main/documentation/contributing/getting-started.md);
`ratingImpactForEarnIn = 5` in the scoring constants). Rating Impact rises when a
contributor rates a note before it reaches a status and their rating matches the status
it then reaches, and falls when their rating is opposite.

So our "newcomers" are newcomers to *writing* only. Every one of them had already rated
enough notes, accurately enough and early enough, to earn in. They are not naive
first-time participants, and the report must say so — it weakens the analogy to Wikipedia
newcomers, where no comparable filter exists.

**Introduced September 2022**, with contributors admitted earlier grandfathered in if
they already had Rating Impact ≥ 5 or Writing Impact ≥ 1. Cohorts before then faced no
such gate.

**Ambiguity.** The exact day is not nailed down. X's product blog post announcing the
change (`blog.x.com/en_us/topics/product/2022/birdwatch-getting-new-onboarding-process-more-visible-notes`)
returns 403 to us, so the September 2022 date rests on contemporaneous trade coverage
([Social Media Today](https://www.socialmediatoday.com/news/twitter-adds-new-qualification-process-for-community-notes-to-improve-note/639369/),
[Adweek](https://www.adweek.com/media/twitter-tweaks-eligibility-requirements-for-community-notes/))
rather than the primary source. It predates the cohorts we can actually use (flag 2), so
it does not affect the analysis — only the sentence in the report.

## 3. AI note writers

**Identifiable, cleanly, and material.**

X opened the AI Note Writer API on **2025-07-01**
([announcement](https://x.com/CommunityNotes/status/1940132205486915917)), admitting a
first cohort later that month. AI writers propose notes; they cannot rate. Like humans
they must earn the ability to write, and can lose it
([`api/overview.md`](https://github.com/twitter/communitynotes/blob/main/documentation/api/overview.md)).

The public data marks them. `userEnrollment.enrollmentState` takes the value
`apiEarnedIn`, documented as "AI note writers publishing notes via the AI Note Writer
API"
([`under-the-hood/download-data.md`](https://github.com/twitter/communitynotes/blob/main/documentation/under-the-hood/download-data.md)).
No heuristic is needed.

In this snapshot:

| | count |
| --- | --- |
| accounts in state `apiEarnedIn` | 37 |
| of those, accounts that wrote at least one note | 35 |
| notes by those accounts | 265,605 (8.6% of all notes) |
| their first note | 2025-09-02 |
| their most recent note | 2026-09-16 |
| authors whose *first* note falls in 2025 / 2026 | 15 / 20 |

As authors they are negligible — 35 out of 343,176 — but as note volume they are 8.6% of
the table and rising, and each one is an extreme outlier on notes written. They are also
not people: an AI writer that stops writing has not "given up", so leaving them in
answers a different question from the one we are asking.

**Two caveats.** `userEnrollment` carries current state only, so an AI account since
moved to another state — `removed`, say — is invisible as such; the 37 is a floor.
And the scoring code defines an `apiEarnedOut` state that does not appear in this
snapshot but could appear in a later one, so any exclusion rule should match the `api`
prefix rather than the exact string `apiEarnedIn`.

---

## Change dates for the cohort discussion (M6c)

Selected from the algorithm changelog in
[`under-the-hood/ranking-notes.md`](https://github.com/twitter/communitynotes/blob/main/documentation/under-the-hood/ranking-notes.md)
and the data changelog in
[`under-the-hood/download-data.md`](https://github.com/twitter/communitynotes/blob/main/documentation/under-the-hood/download-data.md).
Only changes that plausibly move the rate or timing of first verdicts are listed; the
full lists are long and live at those URLs.

| Date | Change | Why it matters here |
| --- | --- | --- |
| 2022-07-18 | `noteStatusHistory` dataset first published | Nothing before it has verdict timestamps (flag 2) |
| 2022-09 | New contributors must earn Rating Impact 5 to write | Defines who a "newcomer" is from here on |
| 2022-10-03 | Rating form updated; statuses resumed for `NOT_MISLEADING` notes written after this date | Before it, that whole class could not resolve |
| 2023-01-17 | Status stabilised once a note is two weeks old | Caps how late a first verdict can arrive |
| 2023-01-20 | All historical notes retro-scored to their status as of 2022-08-15 or two weeks after creation | Pre-2023 verdicts are a batch rewrite, not what reached the contributor at the time |
| 2023-02-24 | Core/Expansion split for global expansion | Cohort composition changes |
| 2024-02-13 | Expanded consensus trial | More notes resolve |
| 2024-04-02 | Single Not Helpful note locks writing when Writing Impact ≤ 0 | **The lockout break. Split cohorts here.** |
| 2024-08-12 | 30-minute CRH stabilisation delay; multi-group models | Shifts verdict timing slightly |
| 2025-03-03 | Minimum delay before any note reaches Helpful | Shifts verdict timing |
| 2025-03-27 | Helpful requires ≥5 positive-factor and ≥5 negative-factor raters | Raises the bar for Helpful |
| 2025-07-01 | AI Note Writer API opens | Start of the population in flag 3 |
| 2025-11-10 | Gaussian model added to final scoring | Changes which notes resolve |

---

## Evidence behind flag 2

Share of notes that ever left NMR, by creation month, from `noteStatusHistory`:

| Month of note creation | Notes | Ever resolved |
| --- | --- | --- |
| 2021-01 … 2022-04 (16 months) | 28,988 | **0 (0.0%)** |
| 2022-05 | 2,503 | 280 (11.2%) |
| 2022-06 … 2022-12 | 18,617 | ~4,600 (25%) |
| 2023 onward | each month | 16–20% |

The field is not merely sparse before 2022-05, it is empty. Combined with the 2023-01-20
retro-scoring, verdicts attached to 2021 and 2022 notes are not the verdicts those
contributors experienced.

By contrast, from 2023 onward the timing is well behaved and supports the day-7 landmark:
median lag from note creation to first verdict is 0.24–0.35 days and the 90th percentile
is 1.5–3.7 days, so a 7-day landmark captures nearly every verdict that will ever arrive.
No note in the snapshot has a verdict timestamp earlier than its creation timestamp, and
`timestampMillisOfFirstNonNMRStatus` is null exactly when `firstNonNMRStatus` is null,
with no `0` or `-1` sentinels.

---

## Decisions

*To be completed by a human at HUMAN GATE 1.*

- Lockout rule: dedicated report section / paragraph / footnote?
- AI authors: excluded? by what rule?
- Cohorts dropped entirely?
- `NOT_MISLEADING` first notes: M5 currently treats this as an optional flag used only in
  M7 robustness. Flag 4 argues it is closer to a structural exclusion. Keep as optional,
  or promote?
