"""M8: the four figures, built from out/tables/ and never from a re-run of the analysis.

Colours are the Okabe-Ito blue / vermillion / bluish-green trio, which passes the
colourblind-separation and chroma checks against a light surface. The same colour means
the same status in every figure.

Usage: python src/figures.py
"""

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "out" / "tables"
FIGS = ROOT / "out" / "figures"

STATUSES = ["Helpful", "Not Helpful", "NMR"]
COLOUR = {"Helpful": "#0072B2", "Not Helpful": "#D55E00", "NMR": "#009E73"}
INK, MUTED = "#1a1a1a", "#666666"
MIN_CELL = 50
RULE_MONTH = "2024-04"

plt.rcParams.update(
    {
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 10,
        "legend.fontsize": 8.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "figure.dpi": 200,
        "pdf.fonttype": 42,
    }
)


def read(name: str) -> list[dict]:
    with open(TABLES / name, newline="") as f:
        return list(csv.DictReader(f))


def style(ax, ylabel: str = "") -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.6)
    ax.set_axisbelow(True)
    if ylabel:
        ax.set_ylabel(ylabel)


def save(fig, name: str) -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGS / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {(FIGS / f'{name}.pdf').relative_to(ROOT)}")


def fig1_newcomers() -> None:
    rows = [r for r in read("by_cohort.csv") if r["cohort_complete"] == "True"]
    months = sorted({r["cohort_month"] for r in rows})
    n = {(r["cohort_month"], r["status"]): int(r["n"]) for r in rows}
    x = range(len(months))

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    bottom = [0.0] * len(months)
    for s in STATUSES:
        vals = [n.get((m, s), 0) for m in months]
        ax.bar(x, vals, bottom=bottom, color=COLOUR[s], label=s, width=0.82,
               edgecolor="white", linewidth=0.6)
        bottom = [b + v for b, v in zip(bottom, vals)]

    style(ax, "New note authors")
    ax.set_xticks([i for i, m in enumerate(months) if m.endswith(("-01", "-07"))])
    ax.set_xticklabels([m for m in months if m.endswith(("-01", "-07"))], rotation=45, ha="right")
    ax.set_xlim(-0.7, len(months) - 0.3)
    ax.legend(frameon=False, loc="upper left", ncol=3)
    ax.set_title("First-note outcome at day 7, by month of first note", loc="left")
    save(fig, "fig1_newcomers")


def fig2_retention() -> None:
    rows = read("primary.csv")
    windows = sorted({int(r["window_days"]) for r in rows})
    by = {(int(r["window_days"]), r["status"]): r for r in rows}

    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    for i, s in enumerate(STATUSES):
        xs = [w + (i - 1) * 1.6 for w in windows]
        ys = [float(by[(w, s)]["proportion"]) for w in windows]
        lo = [ys[j] - float(by[(w, s)]["ci_low"]) for j, w in enumerate(windows)]
        hi = [float(by[(w, s)]["ci_high"]) - ys[j] for j, w in enumerate(windows)]
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt="o", color=COLOUR[s], label=s,
                    markersize=5.5, capsize=3, linewidth=1.6, markeredgecolor="white",
                    markeredgewidth=0.7)
        ax.annotate(f"{ys[-1]:.0%}", (xs[-1], ys[-1]), textcoords="offset points",
                    xytext=(9, -3), color=INK, fontsize=8.5)

    style(ax, "Wrote another note")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xticks(windows)
    ax.set_xticklabels([f"{w} days" for w in windows])
    ax.set_xlabel("Window after day 7")
    ax.set_xlim(22, 108)
    ax.set_ylim(0, 0.5)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("Retention by first-note outcome", loc="left")
    save(fig, "fig2_retention")


def fig3_cohorts() -> None:
    full = [r for r in read("by_cohort.csv") if r["cohort_complete"] == "True"]
    rows = [r for r in full if int(r["n"]) >= MIN_CELL]
    months = sorted({r["cohort_month"] for r in full})
    idx = {m: i for i, m in enumerate(months)}
    series = defaultdict(list)
    for r in rows:
        series[r["status"]].append(
            (idx[r["cohort_month"]], float(r["proportion"]), float(r["ci_low"]), float(r["ci_high"]))
        )

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.axvline(idx[RULE_MONTH], color=MUTED, linewidth=1.0, linestyle=(0, (4, 3)))
    ax.annotate("2024-04 lockout rule", (idx[RULE_MONTH] - 0.6, 0.487), fontsize=7.5,
                color=MUTED, ha="right", va="top")

    for s in STATUSES:
        pts = sorted(series[s])
        xs = [p[0] for p in pts]
        ax.fill_between(xs, [p[2] for p in pts], [p[3] for p in pts],
                        color=COLOUR[s], alpha=0.18, linewidth=0)
        ax.plot(xs, [p[1] for p in pts], color=COLOUR[s], linewidth=1.8, label=s)
        ax.annotate(s, (xs[-1], pts[-1][1]), textcoords="offset points", xytext=(6, -2),
                    color=COLOUR[s], fontsize=8.5, fontweight="bold")

    style(ax, "Wrote another note within 30 days")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xticks([i for i, m in enumerate(months) if m.endswith(("-01", "-07"))])
    ax.set_xticklabels([m for m in months if m.endswith(("-01", "-07"))], rotation=45, ha="right")
    ax.set_xlim(-0.5, len(months) + 7)
    ax.set_ylim(0, 0.5)
    ax.legend(frameon=False, loc="lower left", ncol=3)
    ax.set_title("30-day retention by cohort month, with 95% intervals", loc="left")
    save(fig, "fig3_cohorts")


def fig4_survival() -> None:
    rows = read("km.csv")
    fig, ax = plt.subplots(figsize=(5.8, 3.8))
    for s in STATUSES:
        pts = [r for r in rows if r["status"] == s]
        xs = [0] + [int(r["time_days"]) for r in pts]
        ret = [0.0] + [1 - float(r["survival"]) for r in pts]
        lo = [0.0] + [1 - float(r["ci_high"]) for r in pts]
        hi = [0.0] + [1 - float(r["ci_low"]) for r in pts]
        ax.fill_between(xs, lo, hi, color=COLOUR[s], alpha=0.18, linewidth=0, step="post")
        ax.step(xs, ret, where="post", color=COLOUR[s], linewidth=1.8, label=s)
        ax.annotate(s, (xs[-1], ret[-1]), textcoords="offset points", xytext=(6, -2),
                    color=COLOUR[s], fontsize=8.5, fontweight="bold")

    style(ax, "Returned to write another note")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("Days after the day-7 landmark")
    ax.set_xlim(0, 108)
    ax.set_ylim(0, 0.5)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("Kaplan-Meier return curves, censored at the data cutoff", loc="left")
    save(fig, "fig4_survival")


CAPTIONS = {
    "fig1_newcomers": "Contributors writing their first note each month, split by the status "
    "that note held seven days later. Most first notes never leave Needs More Ratings.",
    "fig2_retention": "Share of contributors who wrote another note within 30, 60 and 90 days "
    "of the day-7 landmark, by the status their first note held at day 7. Bars are 95% Wilson "
    "intervals.",
    "fig3_cohorts": "30-day retention by month of first note. The gap between Not Helpful and "
    "Needs More Ratings is small until April 2024, when a single Not Helpful note began locking "
    "writing ability on its own, and roughly triples thereafter.",
    "fig4_survival": "Kaplan-Meier estimates of the probability of having written another note, "
    "measured from the day-7 landmark and censored at the snapshot's data cutoff. Bands are 95% "
    "intervals.",
}


def main() -> None:
    fig1_newcomers()
    fig2_retention()
    fig3_cohorts()
    fig4_survival()
    FIGS.mkdir(parents=True, exist_ok=True)
    (FIGS / "captions.md").write_text(
        "# Figure captions (draft)\n\nGenerated by `src/figures.py`.\n\n"
        + "\n\n".join(f"**{k}** — {v}" for k, v in CAPTIONS.items())
        + "\n"
    )
    print(f"  wrote {(FIGS / 'captions.md').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
