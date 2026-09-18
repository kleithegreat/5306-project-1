"""Shared retention machinery: the landmark design, and the intervals it is reported with.

M6a, M6c, M6d and M7 all use this, so the landmark rules exist once. Nothing here reads
the contributor table directly — callers pass a sample SQL string, which in practice
always comes from `exclusions.analysis_sql()`.
"""

import math

Z = 1.959963984540054  # normal quantile for 95%

STATUSES = ["Helpful", "Not Helpful", "NMR"]
WINDOWS = [30, 60, 90]


def wilson(x: int, n: int) -> tuple[float, float, float]:
    """Point estimate and Wilson score interval for a proportion."""
    if n == 0:
        return (float("nan"),) * 3
    p = x / n
    d = n + Z**2
    centre = (x + Z**2 / 2) / d
    half = Z / d * math.sqrt(x * (n - x) / n + Z**2 / 4)
    return p, centre - half, centre + half


def newcombe(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float, float]:
    """Newcombe hybrid-score interval for p1 - p2, built from the two Wilson intervals."""
    p1, l1, u1 = wilson(x1, n1)
    p2, l2, u2 = wilson(x2, n2)
    d = p1 - p2
    return (
        d,
        d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2),
        d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2),
    )


def landmark_sql(sample_sql: str, k: int) -> str:
    """Authors observable at day k, classified by the status their first note held then.

    Drops authors who returned before day k — no feedback could have reached them — and
    authors whose day k falls past the data cutoff. A verdict that lands after day k
    counts as NMR here, by design: it had not happened yet.
    """
    mark = f"first_note_at + INTERVAL {k} DAY"
    return f"""
    SELECT *, {mark} AS landmark_at,
      CASE
        WHEN first_verdict_status = 'CURRENTLY_RATED_HELPFUL'
             AND first_verdict_at <= {mark} THEN 'Helpful'
        WHEN first_verdict_status = 'CURRENTLY_RATED_NOT_HELPFUL'
             AND first_verdict_at <= {mark} THEN 'Not Helpful'
        ELSE 'NMR'
      END AS status_k
    FROM ({sample_sql})
    WHERE (second_note_at IS NULL OR second_note_at >= {mark})
      AND {mark} <= data_cutoff_at
    """


def retention_sql(landmark: str, window: int, retained: str | None = None) -> str:
    """Per author: whether the window is fully observed, and whether they came back in it.

    `retained` overrides the definition of coming back — M7 uses it to require two notes
    rather than one.
    """
    end = f"landmark_at + INTERVAL {window} DAY"
    if retained is None:
        retained = f"second_note_at IS NOT NULL AND second_note_at <= {end}"
    return f"""
    SELECT *, {end} <= data_cutoff_at AS observable, ({retained}) AS retained
    FROM ({landmark})
    """


def tabulate(
    con, landmark: str, windows=WINDOWS, group_by: str | None = None, retained: str | None = None
) -> list[dict]:
    """One row per (group, status, window) with n, retained, proportion and Wilson interval."""
    rows = []
    for w in windows:
        cols = f"{group_by}, status_k" if group_by else "status_k"
        q = f"""
        SELECT {cols}, count(*) AS n, count(*) FILTER (WHERE retained) AS retained
        FROM ({retention_sql(landmark, w, retained)}) WHERE observable
        GROUP BY ALL
        """
        for r in con.execute(q).fetchall():
            group, status, n, ret = (r[0], r[1], r[2], r[3]) if group_by else (None, r[0], r[1], r[2])
            p, lo, hi = wilson(ret, n)
            rows.append(
                {
                    "group": group,
                    "status": status,
                    "window_days": w,
                    "n": n,
                    "retained": ret,
                    "proportion": p,
                    "ci_low": lo,
                    "ci_high": hi,
                }
            )
    order = {s: i for i, s in enumerate(STATUSES)}
    rows.sort(key=lambda r: (str(r["group"]), r["window_days"], order.get(r["status"], 9)))
    return rows


def differences(rows: list[dict], against: str = "NMR") -> list[dict]:
    """Status-minus-reference differences with Newcombe intervals, per group and window."""
    by_cell = {(r["group"], r["window_days"], r["status"]): r for r in rows}
    out = []
    for (group, w, status), r in by_cell.items():
        if status == against:
            continue
        ref = by_cell.get((group, w, against))
        if ref is None:
            continue
        d, lo, hi = newcombe(r["retained"], r["n"], ref["retained"], ref["n"])
        out.append(
            {
                "group": group,
                "window_days": w,
                "comparison": f"{status} - {against}",
                "difference": d,
                "ci_low": lo,
                "ci_high": hi,
                "n_status": r["n"],
                "n_reference": ref["n"],
            }
        )
    out.sort(key=lambda r: (str(r["group"]), r["window_days"], r["comparison"]))
    return out
