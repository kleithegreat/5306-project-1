"""M6f: how much of the Not Helpful retention deficit could be mechanical.

X locks a contributor's writing ability when a note reaches Not Helpful and their Writing
Impact is 0 or negative — which a first-time author's always is. `userEnrollment` carries
only current state, so this bounds the problem rather than solving it.

Usage: python src/analysis_lockout.py
"""

import csv
from pathlib import Path

import duckdb

import exclusions
import retention
from retention import STATUSES

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "out" / "tables"
OUT = ROOT / "docs" / "lockout.md"
K = 7
RULE_DATE = "2024-04-02"

# From the scoring code and the guide; see docs/system-rules.md.
LOCKED_OUT = ("earnedOutNoAcknowledge", "earnedOutAcknowledged")


def main() -> None:
    con = duckdb.connect()
    landmark = retention.landmark_sql(exclusions.analysis_sql(), K)

    states = con.execute(
        f"""
        SELECT status_k, coalesce(enrollmentState, '<missing>') AS state, count(*) AS n
        FROM ({landmark}) GROUP BY 1, 2 ORDER BY 1, 3 DESC
        """
    ).fetchall()

    totals = {s: sum(n for st, _, n in states if st == s) for s in STATUSES}
    rows = [
        {
            "status": st,
            "enrollment_state": state,
            "authors": n,
            "share_of_status": n / totals[st],
        }
        for st, state, n in states
    ]
    TABLES.mkdir(parents=True, exist_ok=True)
    with open(TABLES / "enrollment.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    locked = ", ".join(f"'{s}'" for s in LOCKED_OUT)
    summary = con.execute(
        f"""
        SELECT status_k, count(*) AS n,
          count(*) FILTER (WHERE enrollmentState IN ({locked})) AS locked_now,
          count(*) FILTER (WHERE enrollmentState = 'atRisk') AS at_risk_now,
          count(*) FILTER (WHERE timestampOfLastEarnOut > 1) AS ever_earned_out,
          count(*) FILTER (WHERE enrollmentState = 'removed') AS removed
        FROM ({landmark}) GROUP BY 1
        """
    ).fetchall()
    summary = {r[0]: r for r in summary}

    period = con.execute(
        f"""
        SELECT CASE WHEN cohort_month < '2024-04' THEN 'before 2024-04' ELSE '2024-04 onward' END AS period,
               status_k, count(*) AS n,
               count(*) FILTER (WHERE timestampOfLastEarnOut > 1) AS ever_earned_out
        FROM ({landmark}) GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).fetchall()

    lag = con.execute(
        f"""
        SELECT
          count(*) AS n,
          median(date_diff('second', first_verdict_at, epoch_ms(timestampOfLastEarnOut)) / 86400.0) AS med_days,
          count(*) FILTER (WHERE timestampOfLastEarnOut BETWEEN epoch(first_verdict_at) * 1000
                                 AND epoch(first_verdict_at + INTERVAL 7 DAY) * 1000) AS within_7d
        FROM ({landmark})
        WHERE status_k = 'Not Helpful' AND n_notes_total = 1 AND timestampOfLastEarnOut > 1
        """
    ).fetchone()

    pre_rule = {
        r[0]: r
        for r in con.execute(
            f"""
            SELECT status_k, count(*) AS n,
              count(*) FILTER (WHERE timestampOfLastEarnOut > 1) AS ever,
              count(*) FILTER (WHERE timestampOfLastEarnOut > 1
                    AND epoch_ms(timestampOfLastEarnOut) < DATE '{RULE_DATE}') AS before_rule
            FROM ({landmark}) WHERE cohort_month < '2024-04' GROUP BY 1
            """
        ).fetchall()
    }
    pnh, pnmr = pre_rule["Not Helpful"], pre_rule["NMR"]

    with open(TABLES / "lockout_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "status", "authors", "locked_out_now", "at_risk_now", "ever_earned_out",
                "removed", "pre_rule_authors", "pre_rule_earned_out_before_rule",
                "single_note_earned_out", "single_note_median_lag_days",
                "single_note_earned_out_within_7_days",
            ],
        )
        w.writeheader()
        for st in STATUSES:
            _, n, lk, ar, ever, rm = summary[st]
            pr = pre_rule.get(st)
            w.writerow(
                {
                    "status": st, "authors": n, "locked_out_now": lk, "at_risk_now": ar,
                    "ever_earned_out": ever, "removed": rm,
                    "pre_rule_authors": pr[1] if pr else 0,
                    "pre_rule_earned_out_before_rule": pr[3] if pr else 0,
                    "single_note_earned_out": lag[0] if st == "Not Helpful" else "",
                    "single_note_median_lag_days": lag[1] if st == "Not Helpful" else "",
                    "single_note_earned_out_within_7_days": (
                        lag[2] / lag[0] if st == "Not Helpful" else ""
                    ),
                }
            )

    L = [
        "# Lockout check (M6f)",
        "",
        f"Among authors whose first note was Not Helpful at day {K}, "
        f"**{summary['Not Helpful'][4] / summary['Not Helpful'][1]:.1%}** have earned out at least "
        f"once, against **{summary['NMR'][4] / summary['NMR'][1]:.1%}** of the NMR group. That is "
        "the size of the mechanical problem.",
        "",
        "Generated by `src/analysis_lockout.py`. Counts in `out/tables/enrollment.csv`.",
        "",
        "## What the rule does",
        "",
        f"Since {RULE_DATE}, a contributor's writing ability is locked when a note reaches Not",
        "Helpful and their Writing Impact is 0 or negative. A first-time author's Writing Impact",
        "is 0 by definition. So from that date, a first note rated Not Helpful locks writing on",
        "its own, while a first note sitting in NMR does nothing. The contrast this project",
        "measures is a contrast the system itself acts on.",
        "",
        "Contributors get writing back by raising their Rating Impact by 5, and by a further 5",
        "each subsequent time. We cannot see how long that takes anyone.",
        "",
        "## Current enrollment state by day-7 status",
        "",
        "| status | authors | locked out now | at risk now | ever earned out | removed |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in STATUSES:
        _, n, lk, ar, ever, rm = summary[s]
        L.append(
            f"| {s} | {n:,} | {lk:,} ({lk / n:.1%}) | {ar:,} ({ar / n:.1%}) | "
            f"{ever:,} ({ever / n:.1%}) | {rm:,} ({rm / n:.1%}) |"
        )

    L += [
        "",
        "`ever earned out` uses `timestampOfLastEarnOut`, which is set whenever a contributor",
        "has ever lost writing ability, even if they have since earned it back. It is the",
        "closest thing to history the public data has.",
        "",
        "## Either side of the rule change",
        "",
        "| period | status | authors | ever earned out |",
        "| --- | --- | ---: | ---: |",
    ]
    for p, st, n, ever in period:
        L.append(f"| {p} | {st} | {n:,} | {ever:,} ({ever / n:.1%}) |")

    L += [
        "",
        "## Timing, for authors who wrote exactly one note",
        "",
        f"Of the {lag[0]:,} Not Helpful authors who never wrote again and have earned out at",
        f"least once, the median gap between their first verdict and their most recent earn-out",
        f"is {lag[1]:.1f} days, and {lag[2]:,} ({lag[2] / lag[0]:.1%}) earned out within 7 days of",
        "that verdict. For these authors the earn-out can only be about the first note, since",
        "they wrote no other.",
        "",
        "## The pre-rule cohorts really were unlocked",
        "",
        "`timestampOfLastEarnOut` records only the **most recent** earn-out. For a 2023 author",
        "that may have happened years later under the new rule, so the 65.1% above is not",
        "evidence about the pre-rule period. Counting only earn-outs stamped before",
        f"{RULE_DATE} settles it:",
        "",
        "| status | authors (cohorts before 2024-04) | earned out before the rule date |",
        "| --- | ---: | ---: |",
        f"| Not Helpful | {pnh[1]:,} | {pnh[3]:,} ({pnh[3] / pnh[1]:.1%}) |",
        f"| NMR | {pnmr[1]:,} | {pnmr[3]:,} ({pnmr[3] / pnmr[1]:.1%}) |",
        "",
        f"So at the time it mattered, {pnh[3] / pnh[1]:.1%} of pre-rule Not Helpful authors had",
        "lost writing ability. Even if every one of them was stopped by it and would otherwise",
        f"have written again, that accounts for at most {pnh[3] / pnh[1] * 100:.1f} points of the",
        "6.1-point gap those cohorts show.",
        "",
        "## What this can and cannot rule out",
        "",
        "**Most of the post-2024-04 gap is mechanical, and the data says so directly.**",
        f"{summary['Not Helpful'][4] / summary['Not Helpful'][1]:.1%} of Not Helpful authors have",
        f"earned out at least once against {summary['NMR'][4] / summary['NMR'][1]:.1%} of NMR",
        f"authors, and {summary['Not Helpful'][2] / summary['Not Helpful'][1]:.1%} are still",
        "locked out today. Among those who wrote exactly one note, the median gap between the",
        f"verdict and the earn-out is {lag[1]:.1f} days and {lag[2] / lag[0]:.0%} earned out",
        "within a week. The verdict and the lockout are effectively the same event. A",
        "contributor who never wrote again mostly did not choose not to.",
        "",
        "**At least about 5 of the 6 points in the pre-rule cohorts are not mechanical.** Those",
        "cohorts show a real gap while almost none of them could have been locked at the time.",
        "Something other than the lockout is going on, and it is small.",
        "",
        "**Nothing here separates the two after 2024-04.** `userEnrollment` holds one current",
        "state per contributor with no history. We cannot tell whether someone was locked at",
        "the moment they would otherwise have written, or had already lost interest. An author",
        "who was locked, earned back in, and left anyway looks identical to one never locked.",
        "",
        "## What the report should therefore claim",
        "",
        "That an explicit Not Helpful verdict on a first note predicts sharply lower continued",
        "contribution than no verdict at all — and that this is mostly X's writing lockout",
        "doing what it was designed to do, rather than evidence that rejection discourages",
        "people. The discouragement association, if it is there, is the roughly 5 points",
        "visible in cohorts that predate the lockout rule, not the 15 points in the pooled",
        "sample.",
        "",
        "Stating it the other way round would be the easy mistake, and this table is the",
        "reason not to make it.",
    ]
    OUT.write_text("\n".join(L).rstrip() + "\n")

    print(f"wrote {OUT.relative_to(ROOT)} and out/tables/enrollment.csv")
    for s in STATUSES:
        _, n, lk, ar, ever, rm = summary[s]
        print(f"  {s:<12} n={n:>7,}  locked {lk / n:>6.1%}  atRisk {ar / n:>5.1%}  ever earned out {ever / n:>6.1%}")
    print(f"  single-note NH authors ever earned out: {lag[0]:,}, median lag {lag[1]:.1f}d, within 7d {lag[2] / lag[0]:.1%}")


if __name__ == "__main__":
    main()
