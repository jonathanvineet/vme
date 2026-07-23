"""Run the S<->R reconciliation over every panel in DRAWINGS/ that has
an (S) schedule DWG, write one report per panel plus a master rollup.
"""
from __future__ import annotations

from pathlib import Path

from reconcile import DRAWINGS, format_report, reconcile_panel

OUT_DIR = Path(__file__).parent / "out"


def main():
    s_files = sorted(DRAWINGS.glob("*(S).dwg"))
    panels = sorted({p.stem.split("(")[0] for p in s_files})

    OUT_DIR.mkdir(exist_ok=True)
    master_lines = []
    master_lines.append("MASTER BAR TALLY — VME Precast, all panels with an (S) schedule\n")
    master_lines.append(f"{len(panels)} panels found: {', '.join(panels)}\n")

    grand_weight = 0.0
    grand_length = 0.0
    per_panel_totals = []
    dia_grand = {}

    for panel in panels:
        res = reconcile_panel(panel)
        report = format_report(res)
        (OUT_DIR / f"{panel}.txt").write_text(report)

        if res["error"]:
            per_panel_totals.append((panel, None, None, res["error"]))
            continue

        grand_row = next((s for s in res["summary"] if s.dia_mm is None), None)
        panel_wt = grand_row.weight_kg if grand_row else sum(r.weight_kg or 0 for r in res["rows"])
        panel_len = grand_row.total_length_mm if grand_row else sum(r.total_length_mm or 0 for r in res["rows"])
        grand_weight += panel_wt
        grand_length += panel_len
        per_panel_totals.append((panel, panel_wt, panel_len, None))

        for dia, t in res["dia_tally"].items():
            d = dia_grand.setdefault(dia, {"qty": 0, "wt": 0.0, "len": 0.0})
            d["qty"] += t.s_qty
            d["wt"] += t.s_weight_kg
            d["len"] += t.s_length_mm

    master_lines.append("Per-panel totals (from each S sheet's own Summary Schedule):")
    master_lines.append(f"  {'panel':<14}{'weight(kg)':>12}{'length(m)':>12}")
    for panel, wt, length, err in per_panel_totals:
        if err:
            master_lines.append(f"  {panel:<14}{'--':>12}{'--':>12}  {err}")
        else:
            master_lines.append(f"  {panel:<14}{wt:>12.2f}{length/1000:>12.2f}")
    master_lines.append(f"  {'TOTAL':<14}{grand_weight:>12.2f}{grand_length/1000:>12.2f}")
    master_lines.append("")

    master_lines.append("Grand per-diameter rollup (sum across all panels, from S schedules):")
    master_lines.append(f"  {'dia':>5}{'qty':>8}{'length(m)':>12}{'weight(kg)':>12}")
    for dia in sorted(dia_grand):
        d = dia_grand[dia]
        master_lines.append(f"  T{dia:>4.0f}{d['qty']:>8}{d['len']/1000:>12.2f}{d['wt']:>12.2f}")
    master_lines.append(f"  {'ALL':>5}{'':>8}{grand_length/1000:>12.2f}{grand_weight:>12.2f}")

    master_report = "\n".join(master_lines)
    (OUT_DIR / "MASTER_TALLY.txt").write_text(master_report)
    print(master_report)
    print(f"\nPer-panel reports written to {OUT_DIR}/<panel>.txt")


if __name__ == "__main__":
    main()
