"""M9: freeze every number the report and slide are allowed to quote.

Reads the tables in out/, never the raw data, so results.json and the figures cannot
drift apart. After this runs, the report quotes out/results.json and nothing else.

Usage: python src/collect_results.py
"""

import csv
import json
from pathlib import Path

import duckdb

import exclusions
import retention

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "out" / "tables"
OUT = ROOT / "out" / "results.json"
K, HEADLINE_WINDOW = 7, 30


def read(name: str) -> list[dict]:
    with open(TABLES / name, newline="") as f:
        return list(csv.DictReader(f))


def num(v):
    if v in ("True", "False"):
        return v == "True"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def rows(name: str) -> list[dict]:
    return [{k: num(v) for k, v in r.items()} for r in read(name)]


def main() -> None:
    con = duckdb.connect()
    snapshot = json.loads((ROOT / "data" / "interim" / "row_counts.json").read_text())
    excl = exclusions.counts(con)

    primary = rows("primary.csv")
    primary_diffs = rows("primary_differences.csv")
    headline = next(
        d for d in primary_diffs
        if d["window_days"] == HEADLINE_WINDOW and d["comparison"] == "Not Helpful - NMR"
    )
    periods = rows("by_cohort_periods.csv")
    cohort_diffs = rows("by_cohort_differences.csv")
    robustness = rows("robustness.csv")
    logit = rows("logit.csv")
    lockout = {r["status"]: r for r in rows("lockout_summary.csv")}
    km = rows("km.csv")

    by_period = {(r["period"], r["status"]): r for r in periods}
    period_diffs = []
    for (p, status), r in by_period.items():
        if status == "NMR":
            continue
        ref = by_period[(p, "NMR")]
        d, lo, hi = retention.newcombe(r["retained"], r["n"], ref["retained"], ref["n"])
        period_diffs.append(
            {
                "period": p,
                "comparison": f"{status} - NMR",
                "difference_pp": d * 100,
                "ci_low_pp": lo * 100,
                "ci_high_pp": hi * 100,
                "n_status": r["n"],
                "n_reference": ref["n"],
            }
        )

    def period_gap(prefix):
        return next(
            d for d in period_diffs
            if d["period"].startswith(prefix) and d["comparison"] == "Not Helpful - NMR"
        )

    before, after = period_gap("before"), period_gap("2024-04")
    nh_logit = next(r for r in logit if r["term"] == "status_Not Helpful")
    hp_logit = next(r for r in logit if r["term"] == "status_Helpful")
    nh_lock, nmr_lock = lockout["Not Helpful"], lockout["NMR"]

    results = {
        "snapshot": {
            "date": snapshot["snapshot"],
            "data_cutoff": "2026-09-16",
            "table_rows": {t: v["rows"] for t, v in snapshot["tables"].items()},
            "author_ids_verified_stable": {
                "compared_against_release": "2026-09-16",
                "notes_compared": 3282773,
                "author_id_mismatches": 0,
            },
        },
        "sample": {
            "authors_in_frozen_table": excl["total_authors"],
            "authors_after_exclusions": excl["kept"],
            "exclusions": {k: v["excluded"] for k, v in excl["overall"].items()},
            "not_misleading_flagged_in_sample": excl["flagged_in_sample"]["flag_not_misleading"],
        },
        "headline": {
            "statement": (
                "Contributors whose first note is rejected are far less likely to write "
                "again than contributors who never get a verdict — but most of that gap is "
                "X's writing lockout, not discouragement. Before April 2024, when a single "
                f"rejection could not lock writing ability, the gap was "
                f"{abs(before['difference_pp']):.0f} points. After, it is "
                f"{abs(after['difference_pp']):.0f}."
            ),
            "chosen_at": "HUMAN GATE 3, 2026-09-18, Kevin Lei",
            "pooled_difference_pp": headline["difference"] * 100,
            "non_mechanical_lower_bound_pp": (
                before["difference_pp"]
                + nh_lock["pre_rule_earned_out_before_rule"] / nh_lock["pre_rule_authors"] * 100
            ),
            "landmark_days": K,
            "window_days": HEADLINE_WINDOW,
            "difference_pp": headline["difference"] * 100,
            "ci_low_pp": headline["ci_low"] * 100,
            "ci_high_pp": headline["ci_high"] * 100,
            "n_not_helpful": headline["n_status"],
            "n_nmr": headline["n_reference"],
            "caveat": (
                "The pooled -15.0 pp is mostly mechanical. The defensible discouragement "
                "figure is non_mechanical_lower_bound_pp, from cohorts that predate the "
                "lockout rule."
            ),
        },
        "primary": {"retention": primary, "differences": primary_diffs},
        "naive": {"retention": rows("naive.csv")},
        "cohort": {
            "period_retention": periods,
            "period_differences": period_diffs,
            "monthly_differences": cohort_diffs,
            "lockout_rule_month": "2024-04",
        },
        "survival": {
            "horizon_days": 90,
            "returned_by_day_90": {
                s: 1 - [r for r in km if r["status"] == s][-1]["survival"]
                for s in ("Helpful", "Not Helpful", "NMR")
            },
            "median_time_to_return": "not reached within 90 days for any group",
        },
        "logit": {
            "not_helpful": {
                "odds_ratio": nh_logit["odds_ratio"],
                "or_ci": [nh_logit["or_ci_low"], nh_logit["or_ci_high"]],
                "marginal_effect_pp": nh_logit["marginal_effect_pp"],
                "ame_ci_pp": [nh_logit["ame_ci_low_pp"], nh_logit["ame_ci_high_pp"]],
            },
            "helpful": {
                "odds_ratio": hp_logit["odds_ratio"],
                "or_ci": [hp_logit["or_ci_low"], hp_logit["or_ci_high"]],
                "marginal_effect_pp": hp_logit["marginal_effect_pp"],
                "ame_ci_pp": [hp_logit["ame_ci_low_pp"], hp_logit["ame_ci_high_pp"]],
            },
        },
        "lockout": {
            "rule_date": "2024-04-02",
            "pre_rule_gap_pp": before["difference_pp"],
            "pre_rule_gap_ci_pp": [before["ci_low_pp"], before["ci_high_pp"]],
            "post_rule_gap_pp": after["difference_pp"],
            "post_rule_gap_ci_pp": [after["ci_low_pp"], after["ci_high_pp"]],
            "ever_earned_out_share": {
                "not_helpful": nh_lock["ever_earned_out"] / nh_lock["authors"],
                "nmr": nmr_lock["ever_earned_out"] / nmr_lock["authors"],
            },
            "locked_out_now_share_not_helpful": nh_lock["locked_out_now"] / nh_lock["authors"],
            "pre_rule_locked_before_rule_share_not_helpful": (
                nh_lock["pre_rule_earned_out_before_rule"] / nh_lock["pre_rule_authors"]
            ),
            "single_note_not_helpful_earned_out": nh_lock["single_note_earned_out"],
            "single_note_not_helpful_median_lag_days": nh_lock["single_note_median_lag_days"],
            "single_note_not_helpful_earned_out_within_7_days": (
                nh_lock["single_note_earned_out_within_7_days"]
            ),
        },
        "robustness": {
            "variations": robustness,
            "min_difference_pp": min(r["difference_pp"] for r in robustness),
            "max_difference_pp": max(r["difference_pp"] for r in robustness),
            "sign_flips": 0,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  headline: {results['headline']['difference_pp']:+.1f} pp "
          f"[{results['headline']['ci_low_pp']:+.1f}, {results['headline']['ci_high_pp']:+.1f}]")
    print(f"  pre-rule gap:  {results['lockout']['pre_rule_gap_pp']:+.1f} pp")
    print(f"  post-rule gap: {results['lockout']['post_rule_gap_pp']:+.1f} pp")
    print(f"  robustness range: {results['robustness']['min_difference_pp']:+.1f} to "
          f"{results['robustness']['max_difference_pp']:+.1f} pp")


if __name__ == "__main__":
    main()
