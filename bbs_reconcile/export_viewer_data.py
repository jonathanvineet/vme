"""Build per-panel JSON for the 3D viewer: real bar positions/lengths
from the (R) elevation geometry, filtered to only diameters the panel's
own (S) schedule actually calls out (drops cross-paired phantom bars at
diameters that don't exist in the panel - the same class of artifact
documented at length in rebar3d's development).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from bent_bars import synthesize_bent_bars
from castin import extract_sleeves
from geometry import extract_bars
from mark_fill import reconcile_bent_bars, reconcile_straight_bars
from reconcile import DRAWINGS, find_r_sheets
from schedule_extract import parse_schedule_dwg

OUT_DIR = Path(__file__).parent / "out" / "viewer_data"

DIA_COLORS = {
    8: "#8aa0b3",
    10: "#4caf50",
    12: "#3d8bfd",
    16: "#ff9800",
    20: "#e53935",
    25: "#9c27b0",
    32: "#e91e63",
}


def build_panel(panel: str) -> dict | None:
    s_dwg = DRAWINGS / f"{panel}(S).dwg"
    sched = None
    known_dias = set()
    if s_dwg.exists():
        sched = parse_schedule_dwg(s_dwg)
        known_dias = {s.dia_mm for s in sched.summary if s.dia_mm is not None}

    r_sheets = find_r_sheets(panel)
    if not r_sheets:
        return None

    all_bars = []
    elev_bbox = None
    for r in r_sheets:
        bars, bbox = extract_bars(r)
        if bbox is not None and elev_bbox is None:
            elev_bbox = bbox
        all_bars.extend(bars)

    if known_dias:
        all_bars = [b for b in all_bars if b.dia_mm in known_dias]

    if elev_bbox is None:
        return None
    ex0, ex1, ey0, ey1 = elev_bbox

    all_sleeves = []
    for r in r_sheets:
        all_sleeves.extend(extract_sleeves(r, elev_bbox))

    # Real chained bend shapes (assembled from actually-drawn line+arc
    # geometry by geometry.py's chain_bars - genuine U-bars/hooks/L-bends,
    # not schedule guesses) are handled separately from straight bars, and
    # matched to schedule rows FIRST so schedule-driven synthesis only
    # needs to cover whatever real geometry didn't reach.
    straight_pool = [b for b in all_bars if not b.mid_pts]
    chained_pool = [b for b in all_bars if b.mid_pts]

    # Per-mark reconciliation against the (S) schedule: claim real detected
    # bars whose length matches a schedule row, synthesize the disclosed
    # shortfall exactly to the schedule everywhere detection fell short
    # (dense-mesh crossing fragmentation loses 40-60% of weight on most
    # panels - confirmed directly via geo_reconcile.py - so this is not a
    # rare edge case, it's the normal case for T8 mesh bars).
    real_bent, bent_claimed_counts = [], {}
    if sched is not None:
        straight_pool = reconcile_straight_bars(straight_pool, sched, elev_bbox)
        real_bent, bent_claimed_counts = reconcile_bent_bars(chained_pool, sched)

    ox, oy = ex0, ey0  # normalize origin to elevation bbox min
    all_bars = [
        type(b)(b.dia_mm, b.x0 - ox, b.y0 - oy, b.x1 - ox, b.y1 - oy, b.z0, b.z1, b.z_source)
        for b in straight_pool
    ]

    bars_out = []
    for b in all_bars:
        length_mm = math.hypot(b.x1 - b.x0, b.y1 - b.y0)
        weight_kg = (length_mm / 1000.0) * (b.dia_mm ** 2 / 162.0)
        bars_out.append({
            "d": b.dia_mm,
            "p": [[round(b.x0, 1), round(b.y0, 1), round(b.z0, 1)],
                  [round(b.x1, 1), round(b.y1, 1), round(b.z1, 1)]],
            "z_measured": b.z_source == "section",
            "synthesized": b.z_source == "synthesized",
            "len": round(length_mm, 1),
            "wt": round(weight_kg, 3),
        })

    bent_out = []
    for bb in real_bent:
        pts = [[round(x - ox, 1), round(y - oy, 1), round(z, 1)] for x, y, z in bb.points]
        seg_len = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
        bent_out.append({
            "d": bb.dia_mm, "mark": bb.mark, "pts": pts,
            "len": round(seg_len, 1), "wt": round(bb.weight_kg, 3), "measured": True,
        })
    if s_dwg.exists():
        for bb in synthesize_bent_bars(s_dwg, elev_bbox, already_found=bent_claimed_counts):
            pts = [[round(x - ox, 1), round(y - oy, 1), round(z, 1)] for x, y, z in bb.points]
            seg_len = sum(
                math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1)
            )
            bent_out.append({
                "d": bb.dia_mm, "mark": bb.mark, "pts": pts,
                "len": round(seg_len, 1), "wt": round(bb.weight_kg, 3), "measured": False,
            })

    sleeves_out = [
        {"x": round(s.x - ox, 1), "y": round(s.y - oy, 1), "r": round(s.radius_mm, 1)}
        for s in all_sleeves
    ]

    from collections import Counter
    counts = Counter(round(b.dia_mm) for b in all_bars)
    for bb in bent_out:
        counts[round(bb["d"])] = counts.get(round(bb["d"]), 0) + 1
    n_measured = sum(1 for b in all_bars if b.z_source == "section")

    return {
        "panel": panel,
        "width": round(ex1 - ex0, 1),
        "height": round(ey1 - ey0, 1),
        "bars": bars_out,
        "bent_bars": bent_out,
        "sleeves": sleeves_out,
        "counts": dict(sorted(counts.items())),
        "colors": {str(d): DIA_COLORS.get(d, "#cccccc") for d in counts},
        "n_depth_measured": n_measured,
        "n_depth_unknown": len(all_bars) - n_measured,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    s_files = sorted(DRAWINGS.glob("*(S).dwg"))
    panels = sorted({p.stem.split("(")[0] for p in s_files})
    index = []
    for panel in panels:
        data = build_panel(panel)
        if data is None:
            print(f"{panel}: skipped (no elevation geometry found)")
            continue
        (OUT_DIR / f"{panel}.json").write_text(json.dumps(data))
        print(f"{panel}: {len(data['bars'])} bars, counts={data['counts']}")
        index.append(panel)
    (OUT_DIR / "index.json").write_text(json.dumps(index))
    print(f"\nWrote {len(index)} panel JSON files to {OUT_DIR}")


if __name__ == "__main__":
    main()
