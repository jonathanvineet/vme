"""Reconcile an (S) bar-bending-schedule DWG against its (R) rebar-layout
DWG(s) for one panel: full itemized schedule (ground truth weight tally)
+ diameter-level corroboration from R callouts.

Independent, fresh code — does not import or modify anything under
rebar3d/.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from schedule_extract import parse_schedule_dwg, ScheduleDoc
from callouts import parse_callouts, Callout

DRAWINGS = Path("/Users/jonathan/elco/vme/DRAWINGS")


def find_panel_code(s_dwg: Path) -> str:
    return s_dwg.stem.split("(")[0]


def find_r_sheets(panel: str) -> list[Path]:
    out = []
    for p in DRAWINGS.glob("*.dwg"):
        stem = p.stem.strip()
        if not stem.startswith(panel + "("):
            continue
        m = re.search(r"\((R\d*)\)", stem)
        if m:
            out.append(p)
    return sorted(out)


@dataclass
class DiaTally:
    dia_mm: float
    s_qty: int = 0
    s_length_mm: float = 0.0
    s_weight_kg: float = 0.0
    r_count_callouts: int = 0          # sum of explicit "N -T{d}" callout counts
    r_count_callout_instances: int = 0  # number of distinct count-callout texts seen
    r_pitch_callouts: int = 0           # number of "@pitch" spacing callouts (no absolute count)
    r_notes: set = None

    def __post_init__(self):
        if self.r_notes is None:
            self.r_notes = set()


def reconcile_panel(panel: str) -> dict:
    s_dwg = DRAWINGS / f"{panel}(S).dwg"
    result = {
        "panel": panel,
        "s_file": str(s_dwg) if s_dwg.exists() else None,
        "r_files": [],
        "rows": [],
        "summary": [],
        "dia_tally": {},
        "r_callouts_unparsed": [],
        "error": None,
    }
    if not s_dwg.exists():
        result["error"] = f"No (S) schedule DWG found for {panel}"
        return result

    sched: ScheduleDoc = parse_schedule_dwg(s_dwg)
    result["rows"] = sched.rows
    result["summary"] = sched.summary
    if not sched.rows and not sched.summary:
        result["error"] = (
            f"{panel}(S).dwg has no itemized schedule table — only a rebar-shape "
            f"legend/key is present in this file (confirmed against the printed "
            f"{panel}(S).pdf too, 1 page, no schedule text). This looks like a gap "
            f"in the source drawing set, not a parsing failure."
        )
        return result

    tally: dict[float, DiaTally] = {}
    for row in sched.rows:
        if row.dia_mm is None:
            continue
        t = tally.setdefault(row.dia_mm, DiaTally(row.dia_mm))
        t.s_qty += row.quantity or 0
        t.s_length_mm += row.total_length_mm or 0.0
        t.s_weight_kg += row.weight_kg or 0.0

    r_sheets = find_r_sheets(panel)
    result["r_files"] = [str(p) for p in r_sheets]

    all_callouts: list[Callout] = []
    for r in r_sheets:
        all_callouts.extend(parse_callouts(r))

    for c in all_callouts:
        if c.dia_mm != c.dia_mm:  # NaN -> mark-reference or genuinely unparsed
            if c.note != "MARK_REF":
                result["r_callouts_unparsed"].append(c.text)
            continue
        t = tally.setdefault(c.dia_mm, DiaTally(c.dia_mm))
        if c.count is not None:
            t.r_count_callouts += c.count
            t.r_count_callout_instances += 1
        elif c.pitch_mm is not None:
            t.r_pitch_callouts += 1
        if c.note:
            t.r_notes.add(c.note)

    result["dia_tally"] = dict(sorted(tally.items()))
    return result


def format_report(res: dict) -> str:
    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"PANEL {res['panel']}")
    lines.append(f"{'='*70}")
    if res["error"]:
        lines.append(f"ERROR: {res['error']}")
        return "\n".join(lines)
    lines.append(f"S sheet: {res['s_file']}")
    lines.append(f"R sheet(s): {', '.join(Path(p).name for p in res['r_files']) or '(none found)'}")
    lines.append("")
    lines.append("-- Itemized schedule (from S, exact) --")
    by_sub = defaultdict(list)
    for r in res["rows"]:
        by_sub[r.subsheet].append(r)
    for sub in sorted(by_sub):
        lines.append(f"  [{res['panel']}({sub})]")
        for r in by_sub[sub]:
            dia = r.dia_mm if r.dia_mm is not None else float("nan")
            qty = r.quantity if r.quantity is not None else 0
            bl = r.bar_length_mm if r.bar_length_mm is not None else float("nan")
            tl = r.total_length_mm if r.total_length_mm is not None else float("nan")
            wt = r.weight_kg if r.weight_kg is not None else float("nan")
            lines.append(
                f"    {r.mark:>5}  T{dia:<3.0f} qty={qty:<4} "
                f"len={bl:>7.0f}mm  total={tl:>9.0f}mm  "
                f"wt={wt:>7.2f}kg"
            )
    lines.append("")
    lines.append("-- Per-diameter: S schedule vs R callout evidence --")
    lines.append(f"  {'dia':>5} {'S qty':>7} {'S wt(kg)':>10} | "
                  f"{'R Ncallout-sum':>14} {'R instances':>11} {'R pitch-callouts':>16}  notes")
    grand_s_wt = 0.0
    for dia, t in res["dia_tally"].items():
        grand_s_wt += t.s_weight_kg
        flag = ""
        if t.s_qty and t.r_count_callouts == 0 and t.r_pitch_callouts == 0:
            flag = "  <-- diameter NOT mentioned anywhere in R callouts"
        lines.append(
            f"  T{dia:>4.0f} {t.s_qty:>7} {t.s_weight_kg:>10.2f} | "
            f"{t.r_count_callouts:>14} {t.r_count_callout_instances:>11} {t.r_pitch_callouts:>16}  "
            f"{'; '.join(sorted(t.r_notes)) if t.r_notes else ''}{flag}"
        )
    lines.append("")
    lines.append("-- Summary Schedule (from S, panel's own authoritative total) --")
    for s in res["summary"]:
        dia_txt = f"T{s.dia_mm:.0f}" if s.dia_mm is not None else "GRAND TOTAL"
        lines.append(f"  {dia_txt:>12}  total_len={s.total_length_mm:>9.0f}mm  weight={s.weight_kg:>8.2f}kg")
    if res["r_callouts_unparsed"]:
        uniq = sorted(set(res["r_callouts_unparsed"]))
        lines.append("")
        lines.append(f"-- Unparsed R identifier-layer text ({len(res['r_callouts_unparsed'])} instances) --")
        for u in uniq[:20]:
            lines.append(f"    {u!r}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    panel = sys.argv[1]
    res = reconcile_panel(panel)
    print(format_report(res))
