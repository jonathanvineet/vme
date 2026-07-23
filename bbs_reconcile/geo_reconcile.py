"""Reconcile the (S) bar-bending-schedule against ACTUAL geometry measured
in the (R) rebar-layout DWG - not R's text callouts (that's reconcile.py's
job), the real bar LINES themselves, paired into physical bars via
geometry.extract_bars and tallied per diameter (count/length/weight).

This is the "go into the R file and measure it" check: does the geometry
we can actually reconstruct from R agree with what the schedule claims,
independent of any text labels either sheet carries.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from geometry import extract_bars, Bar
from reconcile import DRAWINGS, find_r_sheets
from schedule_extract import parse_schedule_dwg


def unit_weight_kg_per_m(dia_mm: float) -> float:
    return dia_mm ** 2 / 162.0


@dataclass
class GeoDiaTally:
    dia_mm: float
    s_qty: int = 0
    s_length_mm: float = 0.0
    s_weight_kg: float = 0.0
    g_count: int = 0
    g_length_mm: float = 0.0
    g_weight_kg: float = 0.0
    g_measured_z: int = 0
    g_unknown_z: int = 0


def geo_reconcile_panel(panel: str) -> dict:
    s_dwg = DRAWINGS / f"{panel}(S).dwg"
    result = {
        "panel": panel,
        "s_file": str(s_dwg) if s_dwg.exists() else None,
        "r_files": [],
        "dia_tally": {},
        "error": None,
    }
    if not s_dwg.exists():
        result["error"] = f"No (S) schedule DWG for {panel}"
        return result

    sched = parse_schedule_dwg(s_dwg)
    if not sched.rows:
        result["error"] = f"{panel}(S).dwg has no itemized schedule rows"
        return result

    tally: dict[float, GeoDiaTally] = {}
    for row in sched.rows:
        if row.dia_mm is None:
            continue
        t = tally.setdefault(row.dia_mm, GeoDiaTally(row.dia_mm))
        t.s_qty += row.quantity or 0
        t.s_length_mm += row.total_length_mm or 0.0
        t.s_weight_kg += row.weight_kg or 0.0

    known_dias = {s.dia_mm for s in sched.summary if s.dia_mm is not None} or set(tally.keys())

    r_sheets = find_r_sheets(panel)
    result["r_files"] = [str(p) for p in r_sheets]

    all_bars: list[Bar] = []
    for r in r_sheets:
        bars, _bbox = extract_bars(r)
        all_bars.extend(b for b in bars if b.dia_mm in known_dias)

    for b in all_bars:
        t = tally.setdefault(b.dia_mm, GeoDiaTally(b.dia_mm))
        pts = b.points
        length_mm = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
        wt = (length_mm / 1000.0) * unit_weight_kg_per_m(b.dia_mm)
        t.g_count += 1
        t.g_length_mm += length_mm
        t.g_weight_kg += wt
        if b.z_source == "section":
            t.g_measured_z += 1
        else:
            t.g_unknown_z += 1

    result["dia_tally"] = dict(sorted(tally.items()))
    return result


def format_report(res: dict) -> str:
    lines = [f"{'='*78}", f"PANEL {res['panel']} -- schedule vs MEASURED GEOMETRY (from R)", f"{'='*78}"]
    if res["error"]:
        lines.append(f"ERROR: {res['error']}")
        return "\n".join(lines)
    lines.append(f"S sheet: {res['s_file']}")
    lines.append(f"R sheet(s): {', '.join(Path(p).name for p in res['r_files']) or '(none found)'}")
    lines.append("")
    lines.append(f"  {'dia':>5} | {'S qty':>6} {'S len(m)':>9} {'S wt(kg)':>9} | "
                  f"{'G count':>8} {'G len(m)':>9} {'G wt(kg)':>9} {'z-meas':>7} | "
                  f"{'count Δ%':>9} {'wt Δ%':>8}  flag")
    grand_s_wt = grand_g_wt = 0.0
    flags_total = 0
    for dia, t in res["dia_tally"].items():
        grand_s_wt += t.s_weight_kg
        grand_g_wt += t.g_weight_kg
        count_delta = None
        wt_delta = None
        flag = ""
        if t.s_qty:
            count_delta = 100.0 * (t.g_count - t.s_qty) / t.s_qty
        if t.s_weight_kg:
            wt_delta = 100.0 * (t.g_weight_kg - t.s_weight_kg) / t.s_weight_kg
        if t.g_count == 0 and t.s_qty > 0:
            flag = "<-- NO geometry found at all for this diameter"
            flags_total += 1
        elif wt_delta is not None and abs(wt_delta) > 25:
            flag = f"<-- geometry weight off by >{abs(wt_delta):.0f}%"
            flags_total += 1
        lines.append(
            f"  T{dia:>4.0f} | {t.s_qty:>6} {t.s_length_mm/1000:>9.2f} {t.s_weight_kg:>9.2f} | "
            f"{t.g_count:>8} {t.g_length_mm/1000:>9.2f} {t.g_weight_kg:>9.2f} {t.g_measured_z:>7} | "
            f"{'' if count_delta is None else f'{count_delta:+.0f}%':>9} "
            f"{'' if wt_delta is None else f'{wt_delta:+.0f}%':>8}  {flag}"
        )
    lines.append("")
    grand_delta = 100.0 * (grand_g_wt - grand_s_wt) / grand_s_wt if grand_s_wt else 0.0
    lines.append(f"  GRAND TOTAL: S={grand_s_wt:.2f}kg  measured-geometry={grand_g_wt:.2f}kg  "
                  f"delta={grand_delta:+.1f}%")
    lines.append(f"  {flags_total} diameter(s) flagged as significantly mismatched")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    panel = sys.argv[1]
    res = geo_reconcile_panel(panel)
    print(format_report(res))
