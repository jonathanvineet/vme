"""Row-by-row BBS reconciliation: every official mark (diameter + exact
declared length + quantity) checked against real reconstructed bars,
across every panel. No aggregate kg anywhere -- one line per official row.

Run: python3 row_by_row_report.py > row_by_row_report.txt
"""
import json
import math
import sys
from pathlib import Path

from rebar3d.loader import dwg_to_dxf
from rebar3d.schedule import extract_itemized_bbs_dwg, find_schedule_pdf, parse_itemized_bbs

DRAWINGS = Path("/Users/jonathan/elco/vme/DRAWINGS")
OUT = Path("out")
DXF_CACHE = Path("/tmp/dxfcache")

# panel json name -> (source dwg stem for itemized BBS, S-sheet preferred)
PANELS = [
    ("PC-GF-01", "PC-GF-01(R)"),
    ("PW-01-PW-01", "PW-01-PW-01(R)"),
    ("PW-GF-01", "PW-GF-01(R)"),
    ("PW-GF-02", "PW-GF-02(R)"),
    ("PW-GF-06", "PW-GF-06(R)"),
    ("PW-GF-07", "PW-GF-07(R)"),
    ("PW-GF-09", "PW-GF-09(R)"),
    ("PW-GF-18", "PW-GF-18(R)"),
    ("PW-GF-25", "PW-GF-25(R)"),
    ("PW-GF-26", "PW-GF-26(R)"),
    ("PW-GF-45", "PW-GF-45(R)"),
    ("SS-GF-01", "SS-GF-01(R)"),
]
COMBO_PANELS = [
    ("PW-GF-05", ["PW-GF-05(R1)", "PW-GF-05(R2)"]),
    ("PW-GF-08", ["PW-GF-08(R1)", "PW-GF-08(R2)"]),
    ("PW-GF-09-combo", ["PW-GF-09(R1)", "PW-GF-09(R2)"]),
    ("PW-GF-11", ["PW-GF-11(R1)", "PW-GF-11(R2)"]),
    ("PW-GF-27", ["PW-GF-27(R1)", "PW-GF-27(R2)"]),
    ("PW-GF-30", ["PW-GF-30(R1)", "PW-GF-30(R2)"]),
]


def load_itemized(stem: str):
    """Try (S).dwg first (dedicated summary sheet), then own paper space --
    but ONLY trust (S).dwg when it's the same batch/revision as the (R)
    sheet (same staleness guard cli.py uses): confirmed necessary on
    PW-GF-02, whose (S).dwg is dated 2026-07-21 vs its (R).dwg's
    2026-05-18 -- a different, mismatched revision, not the same document.
    """
    base = stem.split("(")[0]
    src = DRAWINGS / f"{stem}.dwg"
    s_dwg = DRAWINGS / f"{base}(S).dwg"
    if src.exists() and s_dwg.exists() and abs(s_dwg.stat().st_mtime - src.stat().st_mtime) < 7 * 86400:
        dxf = dwg_to_dxf(s_dwg, DXF_CACHE)
        rows = extract_itemized_bbs_dwg(dxf)
        if rows:
            return rows
    if src.exists():
        dxf = dwg_to_dxf(src, DXF_CACHE)
        rows = extract_itemized_bbs_dwg(dxf)
        if rows:
            return rows
    if src.exists():
        for pdf in find_schedule_pdf(src):
            if abs(pdf.stat().st_mtime - src.stat().st_mtime) >= 7 * 86400:
                continue
            rows = parse_itemized_bbs(pdf)
            if rows:
                return rows
    return None


def load_bars(json_names: list[str]):
    bars = []
    for jn in json_names:
        p = OUT / f"{jn}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        bars.extend(d["bars"])
    return bars


def bar_length(b):
    return sum(math.dist(b["pts"][i], b["pts"][i + 1]) for i in range(len(b["pts"]) - 1))


def reconcile(panel_label: str, mark_rows, bars):
    lines = [f"\n=== {panel_label} ===",
             f"{'mark':<6} {'dia':>4} {'qty':>4} {'len_mm':>8} {'found':>6} {'status':>8}"]
    # bucket bars by diameter, sorted by length, each consumed at most once
    by_dia: dict[int, list[float]] = {}
    for b in bars:
        by_dia.setdefault(b["d"], []).append(bar_length(b))
    for dia in by_dia:
        by_dia[dia].sort()

    used: dict[int, list[bool]] = {d: [False] * len(v) for d, v in by_dia.items()}
    n_short = n_over = n_ok = 0
    for m in mark_rows:
        if m.qty <= 0 or m.length_mm <= 0:
            continue
        pool = by_dia.get(m.diameter, [])
        flags = used.setdefault(m.diameter, [False] * len(pool))
        tol = max(30.0, 0.08 * m.length_mm)
        found = 0
        for i, length in enumerate(pool):
            if flags[i]:
                continue
            if abs(length - m.length_mm) <= tol:
                flags[i] = True
                found += 1
                if found >= m.qty:
                    break
        status = "OK" if found == m.qty else ("SHORT" if found < m.qty else "OVER")
        if status == "OK":
            n_ok += 1
        elif status == "SHORT":
            n_short += 1
        else:
            n_over += 1
        lines.append(f"{m.mark:<6} T{m.diameter:<3} {m.qty:>4} {m.length_mm:>8.0f} {found:>6} {status:>8}")
    lines.append(f"  -> {n_ok} OK, {n_short} SHORT, {n_over} OVER (of {n_ok+n_short+n_over} official rows)")
    return "\n".join(lines), (n_ok, n_short, n_over)


def main():
    out_lines = []
    totals = [0, 0, 0]
    for json_name, src_stem in PANELS:
        rows = load_itemized(src_stem)
        if not rows:
            out_lines.append(f"\n=== {json_name} ===\n  (no itemized BBS table found -- summary-only)")
            continue
        bars = load_bars([json_name])
        if not bars:
            out_lines.append(f"\n=== {json_name} ===\n  (no out/{json_name}.json found)")
            continue
        text, counts = reconcile(json_name, rows, bars)
        out_lines.append(text)
        for i in range(3):
            totals[i] += counts[i]

    for label, members in COMBO_PANELS:
        best_rows, best_len = None, 0
        for mstem in members:
            rows = load_itemized(mstem)
            if rows and len(rows) > best_len:
                best_rows, best_len = rows, len(rows)
        if not best_rows:
            out_lines.append(f"\n=== {label} (combined) ===\n  (no itemized BBS table found)")
            continue
        bars = load_bars(members)
        if not bars:
            out_lines.append(f"\n=== {label} (combined) ===\n  (no bars found)")
            continue
        text, counts = reconcile(f"{label} (combined: {', '.join(members)})", best_rows, bars)
        out_lines.append(text)
        for i in range(3):
            totals[i] += counts[i]

    print("\n".join(out_lines))
    print(f"\n\n===== GRAND TOTAL =====\n{totals[0]} OK, {totals[1]} SHORT, {totals[2]} OVER "
          f"(of {sum(totals)} official BBS rows across the whole batch)")


if __name__ == "__main__":
    sys.exit(main())
