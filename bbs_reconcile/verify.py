"""Verify each (S) schedule's own internal arithmetic — does every line
tally against itself and against the sheet's own Summary Schedule?

Three checks per panel:
  1. Row level:  quantity * bar_length_mm == total_length_mm
  2. Row level:  total_length_mm/1000 * dia_mm^2/162 == weight_kg   (kg/m = d^2/162)
  3. Diameter level: sum of that diameter's row weights/lengths == the
     panel's own Summary Schedule line for that diameter
  4. Grand total: sum of Summary Schedule diameter lines == its own
     grand-total line

This checks the drawing's arithmetic against itself — independent of
whether the (R) drawing corroborates it (see reconcile.py for that).
"""
from __future__ import annotations

from pathlib import Path

from schedule_extract import parse_schedule_dwg, ScheduleDoc
from reconcile import DRAWINGS

LEN_TOL_MM = 2.0          # qty*bar_length vs total_length
WEIGHT_REL_TOL = 0.01      # 1% relative
WEIGHT_ABS_TOL = 0.03      # or 0.03kg absolute, whichever is looser


def unit_weight_kg_per_m(dia_mm: float) -> float:
    return dia_mm * dia_mm / 162.0


def close(a, b, abs_tol, rel_tol=0.0):
    if a is None or b is None:
        return False
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def verify_panel(panel: str) -> dict:
    s_dwg = DRAWINGS / f"{panel}(S).dwg"
    out = {"panel": panel, "row_issues": [], "dia_issues": [], "total_issue": None,
           "n_rows": 0, "n_row_ok": 0, "error": None}
    if not s_dwg.exists():
        out["error"] = "no (S) file"
        return out
    doc: ScheduleDoc = parse_schedule_dwg(s_dwg)
    if not doc.rows and not doc.summary:
        out["error"] = "no schedule table in (S) file"
        return out

    out["n_rows"] = len(doc.rows)
    for r in doc.rows:
        row_ok = True
        label = f"[{r.subsheet}] {r.mark} T{r.dia_mm:.0f}"

        if r.quantity is not None and r.bar_length_mm is not None and r.total_length_mm is not None:
            expected_total = r.quantity * r.bar_length_mm
            if not close(expected_total, r.total_length_mm, LEN_TOL_MM):
                row_ok = False
                out["row_issues"].append(
                    f"{label}: qty({r.quantity}) x bar_length({r.bar_length_mm:.0f}mm) = "
                    f"{expected_total:.0f}mm, but sheet says total={r.total_length_mm:.0f}mm "
                    f"(diff {expected_total - r.total_length_mm:+.0f}mm)"
                )
        else:
            row_ok = False
            out["row_issues"].append(f"{label}: missing qty/bar_length/total_length field(s)")

        if r.total_length_mm is not None and r.dia_mm is not None and r.weight_kg is not None:
            expected_wt = (r.total_length_mm / 1000.0) * unit_weight_kg_per_m(r.dia_mm)
            if not close(expected_wt, r.weight_kg, WEIGHT_ABS_TOL, WEIGHT_REL_TOL):
                row_ok = False
                out["row_issues"].append(
                    f"{label}: total_length({r.total_length_mm:.0f}mm) x unit_wt(d^2/162) = "
                    f"{expected_wt:.2f}kg, but sheet says weight={r.weight_kg:.2f}kg "
                    f"(diff {expected_wt - r.weight_kg:+.2f}kg)"
                )
        else:
            row_ok = False
            out["row_issues"].append(f"{label}: missing total_length/dia/weight field(s)")

        if row_ok:
            out["n_row_ok"] += 1

    # diameter-level: sum rows per diameter vs the Summary Schedule's own line
    from collections import defaultdict
    per_dia_len = defaultdict(float)
    per_dia_wt = defaultdict(float)
    for r in doc.rows:
        if r.dia_mm is None:
            continue
        per_dia_len[r.dia_mm] += r.total_length_mm or 0.0
        per_dia_wt[r.dia_mm] += r.weight_kg or 0.0

    summary_by_dia = {s.dia_mm: s for s in doc.summary if s.dia_mm is not None}
    grand = next((s for s in doc.summary if s.dia_mm is None), None)

    all_dias = sorted(set(per_dia_len) | set(summary_by_dia))
    for dia in all_dias:
        rows_len = per_dia_len.get(dia, 0.0)
        rows_wt = per_dia_wt.get(dia, 0.0)
        s = summary_by_dia.get(dia)
        if s is None:
            out["dia_issues"].append(f"T{dia:.0f}: rows total {rows_len:.0f}mm/{rows_wt:.2f}kg but no Summary Schedule line for this diameter")
            continue
        if not close(rows_len, s.total_length_mm, LEN_TOL_MM * 2):
            out["dia_issues"].append(
                f"T{dia:.0f}: sum of rows' total_length = {rows_len:.0f}mm, "
                f"Summary Schedule says {s.total_length_mm:.0f}mm (diff {rows_len - s.total_length_mm:+.0f}mm)"
            )
        if not close(rows_wt, s.weight_kg, WEIGHT_ABS_TOL * 3, WEIGHT_REL_TOL):
            out["dia_issues"].append(
                f"T{dia:.0f}: sum of rows' weight = {rows_wt:.2f}kg, "
                f"Summary Schedule says {s.weight_kg:.2f}kg (diff {rows_wt - s.weight_kg:+.2f}kg)"
            )

    if grand is not None:
        sum_len = sum(s.total_length_mm for s in doc.summary if s.dia_mm is not None)
        sum_wt = sum(s.weight_kg for s in doc.summary if s.dia_mm is not None)
        if not close(sum_len, grand.total_length_mm, LEN_TOL_MM * 3):
            out["total_issue"] = out.get("total_issue") or []
        if not close(sum_len, grand.total_length_mm, LEN_TOL_MM * 3) or not close(sum_wt, grand.weight_kg, WEIGHT_ABS_TOL * 5, WEIGHT_REL_TOL):
            out["total_issue"] = (
                f"sum of per-diameter Summary lines = {sum_len:.0f}mm / {sum_wt:.2f}kg, "
                f"but grand total line says {grand.total_length_mm:.0f}mm / {grand.weight_kg:.2f}kg"
            )

    return out


def format_report(v: dict) -> str:
    lines = [f"{'='*70}", f"PANEL {v['panel']} — internal arithmetic check", f"{'='*70}"]
    if v["error"]:
        lines.append(f"SKIPPED: {v['error']}")
        return "\n".join(lines)
    lines.append(f"Rows checked: {v['n_rows']}, tallying cleanly: {v['n_row_ok']}")
    if v["row_issues"]:
        lines.append("\nROW-LEVEL MISMATCHES:")
        for i in v["row_issues"]:
            lines.append(f"  ! {i}")
    else:
        lines.append("  All rows: qty x bar_length = total_length, and total_length x (d^2/162) = weight. CLEAN.")
    if v["dia_issues"]:
        lines.append("\nDIAMETER-LEVEL MISMATCHES (rows sum vs Summary Schedule line):")
        for i in v["dia_issues"]:
            lines.append(f"  ! {i}")
    else:
        lines.append("  Per-diameter row sums match the Summary Schedule lines exactly. CLEAN.")
    if v["total_issue"]:
        lines.append(f"\nGRAND TOTAL MISMATCH:\n  ! {v['total_issue']}")
    else:
        lines.append("  Summary Schedule per-diameter lines sum to its own grand total. CLEAN.")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        panels = sys.argv[1:]
    else:
        panels = sorted({p.stem.split("(")[0] for p in DRAWINGS.glob("*(S).dwg")})
    any_issue = False
    for panel in panels:
        v = verify_panel(panel)
        print(format_report(v))
        print()
        if v["row_issues"] or v["dia_issues"] or v["total_issue"]:
            any_issue = True
    print("RESULT:", "ISSUES FOUND — see above" if any_issue else "ALL PANELS CLEAN")
