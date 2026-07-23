"""Reconcile geometry-detected straight bars against the (S) schedule
PER MARK (not just per-diameter): claim real detected bars whose length
matches a schedule row within tolerance, and synthesize the remaining
count/length exactly as the schedule specifies wherever detection came
up short.

Why: direct measurement (geo_reconcile.py) confirmed dense-mesh crossing
fragmentation causes the line-pairing reconstruction to lose 40-60% of
total weight on most panels, and even the bars it does recover average
noticeably shorter than the real schedule length - not evenly spread
noise, a systematic undercount. Rather than leave the viewer visibly
wrong, apply the same synthesis philosophy already used for bent bars
and diagonal mirror-fill: real geometry wins whenever it matches a
schedule row, synthetic position fills the honest, disclosed gap where
it doesn't - so per-mark count/length/weight always ties out exactly to
the schedule, and the viewer still shows a real measured position for
every bar detection actually earned.
"""
from __future__ import annotations

import math
from pathlib import Path

from bent_bars import BentBar, _nonzero_segments
from geometry import Bar
from schedule_extract import ScheduleDoc


def _bar_len(b: Bar) -> float:
    return math.hypot(b.x1 - b.x0, b.y1 - b.y0)


def reconcile_straight_bars(bars: list[Bar], sched: ScheduleDoc, elev_bbox) -> list[Bar]:
    """Only rows with <=1 nonzero shape segment are "straight" in the sense
    this module can place (a single line). Multi-segment rows are bent
    shapes handled separately by bent_bars.py - forcing them through a
    straight-line placement here was the exact mistake that produced a
    schedule-driven "spike" bug earlier in bent_bars.py, so they're
    explicitly excluded rather than guessed at.
    """
    ex0, ex1, ey0, ey1 = elev_bbox
    width, height = ex1 - ex0, ey1 - ey0

    rows = [
        r for r in sched.rows
        if r.dia_mm is not None and r.quantity and r.bar_length_mm
        and len(_nonzero_segments(r)) <= 1
    ]
    rows.sort(key=lambda r: r.bar_length_mm, reverse=True)

    pool: dict[float, list[Bar]] = {}
    for b in bars:
        pool.setdefault(b.dia_mm, []).append(b)

    out: list[Bar] = []
    for row in rows:
        cands = pool.get(row.dia_mm, [])
        tol = max(80.0, 0.15 * row.bar_length_mm)
        matches = sorted(
            (b for b in cands if abs(_bar_len(b) - row.bar_length_mm) <= tol),
            key=lambda b: abs(_bar_len(b) - row.bar_length_mm),
        )
        claimed = matches[: row.quantity]
        for b in claimed:
            cands.remove(b)
            out.append(b)

        shortfall = row.quantity - len(claimed)
        if shortfall <= 0:
            continue

        # orientation: prefer whatever the claimed real bars showed, else
        # infer from how well this row's length matches the panel's own
        # width/height, else default horizontal (typical mesh convention
        # in this drawing set)
        if claimed:
            horiz_votes = sum(1 for b in claimed if abs(b.y1 - b.y0) < abs(b.x1 - b.x0))
            horizontal = horiz_votes >= (len(claimed) - horiz_votes)
        else:
            horizontal = abs(row.bar_length_mm - width) <= abs(row.bar_length_mm - height)

        L = row.bar_length_mm
        for k in range(shortfall):
            if claimed:
                # place near an already-claimed real sibling of the same
                # mark, mirrored/offset, rather than an arbitrary grid
                # slot - keeps synthesized position close to known-true
                # position wherever any real evidence exists at all
                src = claimed[k % len(claimed)]
                if horizontal:
                    cx = width - ((src.x0 + src.x1) / 2 - ex0) if len(claimed) == 1 else (src.x0 + src.x1) / 2 - ex0
                    cy = (src.y0 + src.y1) / 2 - ey0
                else:
                    cx = (src.x0 + src.x1) / 2 - ex0
                    cy = height - ((src.y0 + src.y1) / 2 - ey0) if len(claimed) == 1 else (src.y0 + src.y1) / 2 - ey0
            else:
                frac = (k + 0.5) / shortfall
                cx = frac * width
                cy = frac * height
            if horizontal:
                cx = min(max(cx, L / 2), max(width - L / 2, L / 2))
                x0, y0, x1, y1 = ex0 + cx - L / 2, ey0 + cy, ex0 + cx + L / 2, ey0 + cy
            else:
                cy = min(max(cy, L / 2), max(height - L / 2, L / 2))
                x0, y0, x1, y1 = ex0 + cx, ey0 + cy - L / 2, ex0 + cx, ey0 + cy + L / 2
            out.append(Bar(row.dia_mm, x0, y0, x1, y1, 0.0, 0.0, "synthesized"))

    return out


def _poly_total_len(pts: list[tuple[float, float]]) -> float:
    return sum(math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]) for k in range(len(pts) - 1))


def reconcile_bent_bars(chained_bars: list[Bar], sched: ScheduleDoc) -> tuple[list[BentBar], dict[str, int]]:
    """Match REAL chained bend shapes (geometry.py's chain_bars - assembled
    from actually-drawn line+arc geometry, not schedule synthesis) to
    multi-segment schedule rows by total length. Returns the matched real
    shapes plus a per-mark claimed count, so bent_bars.py's schedule-driven
    synthesis only needs to fill whatever's left over."""
    rows = [
        r for r in sched.rows
        if r.dia_mm is not None and r.quantity and len(_nonzero_segments(r)) >= 2
    ]
    rows.sort(key=lambda r: sum(_nonzero_segments(r)), reverse=True)

    pool: dict[float, list[Bar]] = {}
    for b in chained_bars:
        pool.setdefault(b.dia_mm, []).append(b)

    out: list[BentBar] = []
    claimed_counts: dict[str, int] = {}
    for row in rows:
        target_len = sum(_nonzero_segments(row))
        cands = pool.get(row.dia_mm, [])
        tol = max(120.0, 0.2 * target_len)
        matches = sorted(
            (b for b in cands if abs(_poly_total_len(b.points) - target_len) <= tol),
            key=lambda b: abs(_poly_total_len(b.points) - target_len),
        )
        claimed = matches[: row.quantity]
        for b in claimed:
            cands.remove(b)
            pts = [(x, y, 0.0) for x, y in b.points]
            wt = (target_len / 1000.0) * (row.dia_mm ** 2 / 162.0)
            out.append(BentBar(row.dia_mm, row.mark, pts, wt))
        if claimed:
            claimed_counts[row.mark] = claimed_counts.get(row.mark, 0) + len(claimed)

    return out, claimed_counts
