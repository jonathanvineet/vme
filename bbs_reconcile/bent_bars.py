"""Synthesize bent bars (any multi-segment shape - hairpins, L/Z-bends,
open links, whatever the shape code implies) from the (S) schedule's own
exact segment data, for marks the straight-line elevation reconstruction
cannot see at all.

Why synthesis and not detection: checked directly against the raw DWG
geometry (2026-07) - candidate "connector" segments matching a bend's
length are indistinguishable from ordinary mesh-crossing fragmentation
noise (487 candidates found vs. ~163 real hairpin bars expected for one
panel, no reliable way to tell them apart). The schedule's shape/length/
quantity/weight numbers are exact (verified independently in
bbs_reconcile's reconciliation work); only the true in-panel *position*
of each bent bar is unknown. So: render the real segment lengths as a
schematic zig-zag polyline (each leg's length is exact, total length/
weight is exact, the specific bend *angles* are not - real bends may not
all be 90 degrees) at an estimated position, spread evenly across the
panel, and flag clearly as position-estimated - matching the honesty bar
set by z_measured for depth.

History: an earlier version only rendered the symmetric 3-segment
"hairpin/staple" case and forced every other multi-segment shape through
that same symmetric path, which stretched an asymmetric shape (mark I/I1,
1140/500/7350mm) into a ~7m spike towering over the panel (caught via
screenshot review). This version renders any nonzero-segment count
generically instead of special-casing one shape family, which removes
that failure mode entirely rather than patching around it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from schedule_extract import parse_schedule_dwg, BarRow

SEG_ORDER = ["A", "B", "C", "D", "E", "G"]
# cycle right / up / left / down so consecutive segments visibly turn,
# without claiming to know the drawing's real bend angles
_DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]


@dataclass
class BentBar:
    dia_mm: float
    mark: str
    points: list  # [(x,y,z), ...] polyline in mm, position already placed within panel
    weight_kg: float


def _nonzero_segments(row: BarRow) -> list[float]:
    return [row.segments.get(k, 0.0) or 0.0 for k in SEG_ORDER if (row.segments.get(k, 0.0) or 0.0) > 1e-6]


def _classify_hairpin(row: BarRow):
    """Kept for callers that specifically want to know if a row is a
    symmetric 3-segment hairpin (used by mark_fill.py to exclude bent
    shapes from the straight-bar pool). Returns (leg1, bend, leg2) or None.
    """
    segs = _nonzero_segments(row)
    if len(segs) != 3:
        return None
    leg1, bend, leg2 = segs
    if abs(leg1 - leg2) > 0.3 * max(leg1, leg2):
        return None
    if bend >= min(leg1, leg2):
        return None
    return leg1, bend, leg2


def _local_polyline(segs: list[float]):
    """Build a local schematic zig-zag polyline for the given segment
    lengths, returning (points, width, height) of its bounding box."""
    pts = [(0.0, 0.0)]
    x, y = 0.0, 0.0
    for i, seg_len in enumerate(segs):
        dx, dy = _DIRS[i % 4]
        x += dx * seg_len
        y += dy * seg_len
        pts.append((x, y))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return pts, (max(xs) - min(xs)) or 1.0, (max(ys) - min(ys)) or 1.0, min(xs), min(ys)


def synthesize_bent_bars(
    panel_dwg: Path,
    elev_bbox: tuple[float, float, float, float],
    already_found: dict[str, int] | None = None,
) -> list[BentBar]:
    """already_found: mark -> count already recovered from REAL chained
    geometry (geometry.py's chain_bars) - only the schedule's remaining
    shortfall for that mark gets synthesized here, same disclosed-gap
    philosophy as mark_fill.py uses for straight bars."""
    sched = parse_schedule_dwg(panel_dwg)
    ex0, ex1, ey0, ey1 = elev_bbox
    width, height = ex1 - ex0, ey1 - ey0
    already_found = already_found or {}

    bent_rows = []
    for row in sched.rows:
        segs = _nonzero_segments(row)
        if len(segs) < 2 or not row.quantity or not row.dia_mm:
            continue
        bent_rows.append((row, segs))

    out: list[BentBar] = []
    for row, segs in bent_rows:
        qty = row.quantity - already_found.get(row.mark, 0)
        if qty <= 0:
            continue
        local_pts, lw, lh, lx0, ly0 = _local_polyline(segs)

        pitch = max(width / max(qty, 1), lw + 20.0)
        cols = max(1, min(qty, int(width / pitch) or 1))
        rows_needed = math.ceil(qty / cols)
        row_pitch = max(height / max(rows_needed, 1), lh + 20)

        total_len_m = sum(segs) / 1000.0
        wt = total_len_m * (row.dia_mm ** 2 / 162.0)

        n = 0
        for ri in range(rows_needed):
            if n >= qty:
                break
            cy = min(ri * row_pitch + lh / 2, height - lh / 2) if height > lh else height / 2
            cy = max(cy, lh / 2)
            for ci in range(cols):
                if n >= qty:
                    break
                cx = (ci + 0.5) * (width / cols)
                ox = ex0 + cx - lw / 2 - lx0
                oy = ey0 + cy - lh / 2 - ly0
                pts = [(ox + px, oy + py, 0.0) for px, py in local_pts]
                out.append(BentBar(row.dia_mm, row.mark, pts, wt))
                n += 1
    return out
