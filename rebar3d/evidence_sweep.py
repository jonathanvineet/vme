"""For every SHORT row in row_by_row_report, check whether real matching-
length geometry exists ANYWHERE in the source DXF (all views), regardless
of position. This is the fast, reliable test proven today: zero evidence
= genuine dead end; evidence >= remaining need = likely a fixable pipeline
gap worth investigating.
"""
import json
import math
import sys
from pathlib import Path

from rebar3d.loader import dwg_to_dxf, load_entities
from rebar3d.views import cluster_views
from rebar3d.extract import extract_bars
from rebar3d.reconstruct import snap_diameter
from rebar3d.schedule import extract_itemized_bbs_dwg, find_schedule_pdf, parse_itemized_bbs

DRAWINGS = Path("/Users/jonathan/elco/vme/DRAWINGS")
OUT = Path("out")
DXF_CACHE = Path("/tmp/dxfcache")

PANELS = [
    # (panel_label, [source dwg stems for itemized BBS], [out/*.json basenames])
    ("PC-GF-01", ["PC-GF-01(R)"], ["PC-GF-01"]),
    ("PW-01-PW-01", ["PW-01-PW-01(R)"], ["PW-01-PW-01"]),
    ("PW-GF-01", ["PW-GF-01(R)"], ["PW-GF-01"]),
    ("PW-GF-06", ["PW-GF-06(R)"], ["PW-GF-06"]),
    ("PW-GF-07", ["PW-GF-07(R)"], ["PW-GF-07"]),
    ("PW-GF-18", ["PW-GF-18(R)"], ["PW-GF-18"]),
    ("PW-GF-25", ["PW-GF-25(R)"], ["PW-GF-25"]),
    ("PW-GF-26", ["PW-GF-26(R)"], ["PW-GF-26"]),
    ("PW-GF-05", ["PW-GF-05(R1)", "PW-GF-05(R2)"], ["PW-GF-05(R1)", "PW-GF-05(R2)"]),
    ("PW-GF-08", ["PW-GF-08(R1)", "PW-GF-08(R2)"], ["PW-GF-08(R1)", "PW-GF-08(R2)"]),
    ("PW-GF-09-combo", ["PW-GF-09(R1)", "PW-GF-09(R2)"], ["PW-GF-09(R1)", "PW-GF-09(R2)"]),
    ("PW-GF-11", ["PW-GF-11(R1)", "PW-GF-11(R2)"], ["PW-GF-11(R1)", "PW-GF-11(R2)"]),
    ("PW-GF-27", ["PW-GF-27(R1)", "PW-GF-27(R2)"], ["PW-GF-27(R1)", "PW-GF-27(R2)"]),
    ("PW-GF-30", ["PW-GF-30(R1)", "PW-GF-30(R2)"], ["PW-GF-30(R1)", "PW-GF-30(R2)"]),
]


def load_itemized(stem: str):
    base = stem.split("(")[0]
    src = DRAWINGS / f"{stem}.dwg"
    s_dwg = DRAWINGS / f"{base}(S).dwg"
    if src.exists() and s_dwg.exists() and abs(s_dwg.stat().st_mtime - src.stat().st_mtime) < 7 * 86400:
        rows = extract_itemized_bbs_dwg(dwg_to_dxf(s_dwg, DXF_CACHE))
        if rows:
            return rows
    if src.exists():
        rows = extract_itemized_bbs_dwg(dwg_to_dxf(src, DXF_CACHE))
        if rows:
            return rows
        for pdf in find_schedule_pdf(src):
            if abs(pdf.stat().st_mtime - src.stat().st_mtime) >= 7 * 86400:
                continue
            rows = parse_itemized_bbs(pdf)
            if rows:
                return rows
    return None


def bar_length(b):
    return sum(math.dist(b["pts"][i], b["pts"][i + 1]) for i in range(len(b["pts"]) - 1))


def main():
    for panel_label, members, json_names in PANELS:
        best_rows, best_len, best_stem = None, 0, None
        for mstem in members:
            rows = load_itemized(mstem)
            if rows and len(rows) > best_len:
                best_rows, best_len, best_stem = rows, len(rows), mstem
        if not best_rows:
            continue

        bars = []
        for jn in json_names:
            p = OUT / f"{jn}.json"
            if p.exists():
                bars.extend(json.loads(p.read_text())["bars"])
        by_dia_cur = {}
        for b in bars:
            by_dia_cur.setdefault(b["d"], []).append(bar_length(b))
        for d in by_dia_cur:
            by_dia_cur[d].sort()

        # whole-DXF raw candidates across ALL member sheets' ALL views
        by_dia_raw = {}
        for mstem in members:
            src = DRAWINGS / f"{mstem}.dwg"
            if not src.exists():
                continue
            ents = load_entities(dwg_to_dxf(src, DXF_CACHE))
            for v in cluster_views(ents):
                for b in extract_bars(v.ents, min_len=50.0):
                    d = snap_diameter(b.diameter)
                    if d:
                        by_dia_raw.setdefault(d, []).append(b.length)

        print(f"\n=== {panel_label} (source: {best_stem}) ===")
        used_cur = {d: [False] * len(v) for d, v in by_dia_cur.items()}
        # Track which RAW candidates have already been credited to an
        # earlier mark at the same diameter -- without this, three marks
        # all wanting ~4375mm each independently "see" the same single
        # unclaimed raw bar and each get flagged POSSIBLE BUG, when only
        # ONE of them could ever actually claim it. Confirmed on
        # PW-GF-06's M1/M2/M3 (all target 4375mm): only 1 real DXF
        # candidate exists beyond what mark M already claims, but all
        # three showed "raw=1" independently before this fix.
        raw_used = {d: [False] * len(v) for d, v in by_dia_raw.items()}
        for m in sorted(best_rows, key=lambda m: m.length_mm):
            if m.qty <= 0 or m.length_mm <= 0:
                continue
            tol = max(30.0, 0.08 * m.length_mm)
            pool = by_dia_cur.get(m.diameter, [])
            flags = used_cur.setdefault(m.diameter, [False] * len(pool))
            found = 0
            for i, length in enumerate(pool):
                if flags[i]:
                    continue
                if abs(length - m.length_mm) <= tol:
                    flags[i] = True
                    found += 1
                    if found >= m.qty:
                        break
            raw_pool = by_dia_raw.get(m.diameter, [])
            raw_flags = raw_used.setdefault(m.diameter, [False] * len(raw_pool))
            unclaimed_raw = 0
            for i, length in enumerate(raw_pool):
                if raw_flags[i]:
                    continue
                if abs(length - m.length_mm) <= tol:
                    raw_flags[i] = True
                    unclaimed_raw += 1
            if found >= m.qty:
                continue  # OK row, skip
            verdict = "DEAD END (zero evidence)" if not unclaimed_raw else (
                f"POSSIBLE BUG (unclaimed_raw={unclaimed_raw} vs found={found}/{m.qty})"
                if unclaimed_raw > found else "DEAD END (evidence already fully used)")
            print(f"  {m.mark:<6} T{m.diameter:<3} need={m.qty:<3} len={m.length_mm:<7.0f} "
                  f"found={found:<3} unclaimed_raw={unclaimed_raw:<3} {verdict}")


if __name__ == "__main__":
    sys.exit(main())
