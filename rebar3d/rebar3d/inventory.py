"""Exhaustive per-DWG inventory + full reconciliation against every official doc.

Answers "are we getting EVERYTHING out of the drawings?" head-on: for each DWG
this dumps a complete categorized census of every entity (modelspace geometry
by layer/type, block inserts by name, every text string, every paper-space
table), the reconstruction's own census, and then reconciles the three
independent sources of truth against each other:

  raw DWG geometry  <->  reconstruction (out/<panel>.json)
  reconstruction    <->  Summary Schedule (paper space / R-PDF, per-diameter)
  reconstruction    <->  itemized BBS PDF (row-by-row, where the doc exists)

Nothing is silently dropped: the census counts every entity, and the
reconciliation names each gap instead of hiding it inside an aggregate total.

Run:  python3 -m rebar3d.inventory [drawings_dir] [-o out] [--report FILE]
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .loader import dwg_to_dxf, load_entities
from .schedule import ScheduleRow, extract_schedule_dwg

STD_DIA = (8, 10, 12, 16, 20, 25, 32)


# ---------------------------------------------------------------- BBS PDF ---

@dataclass
class BBSRow:
    sno: int
    desc: str
    spacing: str
    dia: int
    nos: int
    segments: list[float]
    length_m: float        # one bar
    total_length_m: float
    weight_kg: float


def parse_bbs_pdf(pdf_path: Path) -> list[BBSRow] | None:
    """Parse an itemized office BBS PDF (S.No / Description / ... / Weight).

    These are the separate per-panel BBS docs (e.g. DRAWINGS/PW-GF-09.pdf,
    no "(R)" in the name) — NOT the R-sheet's Summary Schedule.
    """
    try:
        import pypdf
    except ImportError:
        return None
    if not pdf_path.exists():
        return None
    text = "\n".join(p.extract_text() for p in pypdf.PdfReader(str(pdf_path)).pages)
    rows: list[BBSRow] = []
    # e.g. "10 Vertical Bar 150c/c 8 120 0.4 0.1 0.4 - - - 0.868 104.16 0.395 41.1496"
    pat = re.compile(
        r"^(\d+)\s+(.+?)\s+([\d.]+\s*[cC]/[cC]|-)\s+(\d+)\s+(\d+)\s+"
        r"((?:[\d.]+|-)(?:\s+(?:[\d.]+|-)){5})\s+"
        r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$",
        re.M,
    )
    for m in pat.finditer(text):
        segs = [float(s) for s in m.group(6).split() if s != "-"]
        rows.append(BBSRow(
            sno=int(m.group(1)), desc=m.group(2).strip(),
            spacing=m.group(3).replace(" ", ""), dia=int(m.group(4)),
            nos=int(m.group(5)), segments=segs,
            length_m=float(m.group(7)), total_length_m=float(m.group(8)),
            weight_kg=float(m.group(10)),
        ))
    return rows or None


def find_bbs_pdf(dwg_path: Path) -> Path | None:
    """The itemized BBS doc for a panel: '<PANEL>.pdf' with no sheet suffix."""
    base = re.sub(r"\(.*\)", "", dwg_path.stem).strip()
    for cand in (dwg_path.parent / f"{base}.pdf",
                 dwg_path.parent / f"{base} .pdf"):
        if cand.exists():
            return cand
    return None


# ------------------------------------------------------------- raw census ---

@dataclass
class RawCensus:
    total_entities: int = 0
    by_layer_kind: Counter = field(default_factory=Counter)   # (layer, kind) -> n
    blocks: Counter = field(default_factory=Counter)          # block name -> instances
    line_len_by_layer: Counter = field(default_factory=Counter)  # layer -> mm drawn
    texts: Counter = field(default_factory=Counter)           # normalized string -> n
    paper_texts: list[tuple[str, float, float]] = field(default_factory=list)


def raw_census(dxf_path: Path) -> RawCensus:
    c = RawCensus()
    ents = load_entities(dxf_path)
    seen_bref: set[int] = set()
    for e in ents:
        c.total_entities += 1
        c.by_layer_kind[(e.layer, e.kind)] += 1
        if e.block and e.bref not in seen_bref:
            seen_bref.add(e.bref)
            c.blocks[e.block] += 1
        if e.kind in ("LINE", "LWPOLYLINE") and len(e.points) >= 2:
            c.line_len_by_layer[e.layer] += sum(
                math.dist(a, b) for a, b in zip(e.points, e.points[1:]))
        elif e.kind in ("ARC", "CIRCLE"):
            frac = 1.0 if e.kind == "CIRCLE" else (
                ((e.end_angle - e.start_angle) % 360) / 360 or 1.0)
            c.line_len_by_layer[e.layer] += 2 * math.pi * e.radius * frac
        if e.kind in ("TEXT", "MTEXT") and e.text.strip():
            c.texts[" ".join(e.text.split())] += 1

    # paper space text (schedules, title block) — modelspace-only loading
    # famously hid the Summary Schedule from this project for weeks
    import ezdxf
    doc = ezdxf.readfile(str(dxf_path))
    for lname in doc.layout_names():
        if lname.lower() == "model":
            continue
        for e in doc.layout(lname):
            if e.dxftype() in ("MTEXT", "TEXT"):
                s = (e.plain_text() if e.dxftype() == "MTEXT"
                     else e.dxf.text).strip()
                if s:
                    c.paper_texts.append(
                        (" ".join(s.split()), e.dxf.insert.x, e.dxf.insert.y))
    return c


_CALLOUT = re.compile(r"(\d+)\s*-\s*T(\d+)")
_PITCH = re.compile(r"T(\d+)\s*(?:[A-Z ]*)?@\s*(\d+)", re.I)


def categorize_texts(texts: Counter) -> dict[str, list[tuple[str, int]]]:
    cats: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for s, n in sorted(texts.items()):
        up = s.upper()
        if _CALLOUT.search(s):
            cats["count callouts (N -Td)"].append((s, n))
        elif _PITCH.search(s) or "@" in s and re.search(r"T\d+", up):
            cats["pitch callouts (Td @p)"].append((s, n))
        elif "UBAR" in up or "U-BAR" in up or "U BAR" in up:
            cats["u-bar callouts"].append((s, n))
        elif "TIE" in up:
            cats["tie callouts"].append((s, n))
        elif re.fullmatch(r"[\d.]+", s):
            cats["dimensions (bare numbers)"].append((s, n))
        elif re.search(r"\bN\d+\b", up):
            cats["insert marks (Nn)"].append((s, n))
        else:
            cats["other annotation"].append((s, n))
    return cats


def paper_tables(paper_texts: list[tuple[str, float, float]]) -> list[str]:
    """Group paper-space text into visual rows (by Y) — a generic dump that
    catches every schedule the sheet carries (Summary / Projecting Bar /
    Dowel Bar / Insert / Weight), not just the one the pipeline consumes."""
    rows_by_y: list[list] = []
    for s, x, y in sorted(paper_texts, key=lambda c: -c[2]):
        for r in rows_by_y:
            if abs(r[0] - y) < 3:
                r[1].append((x, s))
                break
        else:
            rows_by_y.append([y, [(x, s)]])
    out = []
    for _, cl in rows_by_y:
        cl.sort()
        out.append(" | ".join(s for _, s in cl))
    return out


# ---------------------------------------------------- reconstruction side ---

def poly_len(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def recon_census(json_path: Path):
    d = json.loads(json_path.read_text())
    by_kd: dict[tuple[str, int], list[float]] = defaultdict(list)
    for b in d["bars"]:
        by_kd[(b["kind"], b["d"])].append(poly_len(b["pts"]))
    return d, by_kd


def bar_orientation(pts) -> str:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    dx, dy = max(xs) - min(xs), max(ys) - min(ys)
    if dx > 2 * dy:
        return "Horizontal"
    if dy > 2 * dx:
        return "Vertical"
    return "Other"


def match_bbs_rows(bbs: list[BBSRow], bars: list[dict]) -> list[str]:
    """Row-by-row: greedily assign each reconstructed bar to the BBS row it
    best satisfies (same dia, compatible orientation, closest length; a
    folded U-loop of ~2x a straight row's length counts as 2 of that row).
    Totals compared per row — this names WHERE steel is missing instead of
    hiding it in a per-diameter aggregate."""
    # bent kinds (ties, loops, dowels) have no meaningful H/V orientation
    bent = ("tie", "link", "u-bar", "hook", "shape", "face-dowel", "diagonal")
    remaining = [{"dia": b["d"], "len": poly_len(b["pts"]) / 1000,
                  "orient": ("Other" if b["kind"] in bent
                             else bar_orientation(b["pts"])),
                  "kind": b["kind"]}
                 for b in bars]
    rows = [{"r": r, "dia": 16 if r.dia == 15 else r.dia,  # T15 = T16 typo
             "cap": r.nos, "found": 0.0, "n": 0}
            for r in sorted(bbs, key=lambda r: r.sno)]

    def orient_ok(row, b):
        desc = row["r"].desc.lower()
        want = ("Horizontal" if "horizontal" in desc else
                "Vertical" if "vertical" in desc else None)
        return (want is None or b["orient"] == "Other" or b["orient"] == want)

    # bar-centric best-fit: each bar picks the row whose per-bar length it
    # matches best (pass 1 = one booked bar; pass 2 = a folded loop that
    # books as two bars, e.g. a U-folded pair of straight mesh bars).
    for units, lo, hi in ((1, 0.75, 1.30), (2, 1.75, 2.45)):
        for b in sorted(remaining, key=lambda b: -b["len"]):
            if b.get("used"):
                continue
            cands = [(abs(b["len"] / (units * row["r"].length_m) - 1), row)
                     for row in rows
                     if row["dia"] == b["dia"] and row["cap"] >= units
                     and row["r"].length_m
                     and lo <= b["len"] / row["r"].length_m <= hi
                     and orient_ok(row, b)]
            if cands:
                _, row = min(cands, key=lambda c: c[0])
                b["used"] = True
                row["cap"] -= units
                row["n"] += units
                row["found"] += b["len"]

    lines = []
    tot_official = tot_found = 0.0
    for row in rows:
        r = row["r"]
        pct = (f"{100 * row['found'] / r.total_length_m:.0f}%"
               if r.total_length_m else "-")
        lines.append(
            f"  row {r.sno:>2}  T{r.dia:<2} x{r.nos:<3} {r.desc[:20]:<20}"
            f" {r.length_m:>6.2f}m each | official {r.total_length_m:>7.2f}m"
            f"  matched {row['found']:>7.2f}m ({row['n']:>3}/{r.nos:<3}) {pct:>5}"
            f"  [{r.weight_kg:.1f}kg]")
        tot_official += r.total_length_m
        tot_found += row["found"]
    unmatched = [b for b in remaining if not b.get("used")]
    un_by = Counter((b["kind"], b["dia"]) for b in unmatched)
    un_len = defaultdict(float)
    for b in unmatched:
        un_len[(b["kind"], b["dia"])] += b["len"]
    lines.append(f"  {'':>56}officials {tot_official:>7.2f}m"
                 f"  matched {tot_found:>7.2f}m")
    if unmatched:
        lines.append("  reconstructed bars matching NO BBS row (extra / mis-shaped):")
        for (k, d), n in sorted(un_by.items()):
            lines.append(f"    {k:<12} T{d:<3} x{n:<4} {un_len[(k, d)]:>8.2f}m"
                         f"  ({un_len[(k, d)] * d * d / 162:.1f}kg)")
    return lines


# ------------------------------------------------------------------ report ---

def wt(dia: int, length_mm: float) -> float:
    return (length_mm / 1000) * dia * dia / 162


def panel_report(dwg: Path, out_dir: Path) -> list[str]:
    L: list[str] = [f"\n{'=' * 78}\n## {dwg.name}\n{'=' * 78}"]
    dxf = dwg_to_dxf(dwg, out_dir / "dxf")
    c = raw_census(dxf)

    L.append(f"\n### RAW ENTITY CENSUS  (total {c.total_entities} modelspace"
             f" entities, {len(c.paper_texts)} paper-space text cells)")
    for (layer, kind), n in sorted(c.by_layer_kind.items()):
        mm = c.line_len_by_layer.get(layer, 0)
        L.append(f"  {layer:<22} {kind:<12} x{n}")
    L.append("  drawn linework length by layer (mm):")
    for layer, mm in sorted(c.line_len_by_layer.items(), key=lambda kv: -kv[1]):
        L.append(f"    {layer:<22} {mm:>12.0f}")
    if c.blocks:
        L.append("  block INSERTs:")
        for b, n in sorted(c.blocks.items()):
            L.append(f"    {b:<50} x{n}")

    L.append("\n### TEXT / ANNOTATION CENSUS (modelspace)")
    for cat, items in categorize_texts(c.texts).items():
        L.append(f"  [{cat}] ({sum(n for _, n in items)} instances,"
                 f" {len(items)} distinct)")
        show_all = "callout" in cat or "mark" in cat
        for s, n in (items if show_all else items[:8]):
            L.append(f"    {n:>3}x  {s[:90]}")
        if not show_all and len(items) > 8:
            L.append(f"    ... {len(items) - 8} more distinct strings")

    L.append("\n### PAPER-SPACE TABLES (all schedules on the sheet)")
    rows = paper_tables(c.paper_texts)
    for r in rows:
        if r.strip():
            L.append(f"  {r[:110]}")

    # reconstruction + reconciliation only for sheets the pipeline ran
    name = re.sub(r"\(R\)", "", dwg.stem).strip()
    jpath = out_dir / f"{name}.json"
    is_r = "(R)" in dwg.stem
    if not jpath.exists():
        jpath = out_dir / f"{dwg.stem}.json"
    if jpath.exists():
        d, by_kd = recon_census(jpath)
        L.append(f"\n### RECONSTRUCTION CENSUS  ({len(d['bars'])} bars)"
                 f"  panel {d['width']:.0f}x{d['height']:.0f}x{d['thickness']:.0f}mm")
        tot = 0.0
        for (kind, dia), lens in sorted(by_kd.items()):
            w = wt(dia, sum(lens))
            tot += w
            L.append(f"  {kind:<12} T{dia:<3} x{len(lens):<4}"
                     f" {sum(lens) / 1000:>8.2f}m {w:>7.2f}kg")
        L.append(f"  {'RECON TOTAL':<21} {'':>8} {tot:>7.2f}kg")
        if d.get("stats", {}).get("features"):
            L.append(f"  features: {d['stats']['features']}")

    if is_r and jpath.exists():
        summary = extract_schedule_dwg(dxf)
        if summary:
            L.append("\n### RECONCILIATION vs SUMMARY SCHEDULE (paper space)")
            found = defaultdict(float)
            for (kind, dia), lens in by_kd.items():
                found[dia] += sum(lens)
            off = {r.diameter: r for r in summary}
            for dia in sorted(set(found) | set(off)):
                wf = wt(dia, found.get(dia, 0.0))
                wo = off[dia].weight_kg if dia in off else 0.0
                lf, lo = found.get(dia, 0) / 1000, (
                    off[dia].length_mm / 1000 if dia in off else 0)
                pct = f"{100 * wf / wo:.0f}%" if wo else "EXTRA"
                L.append(f"  T{dia:<3} len {lf:>7.1f}m vs {lo:>7.1f}m |"
                         f" wt {wf:>7.2f} vs {wo:>7.2f}kg  {wf - wo:>+7.2f}  {pct}")

        bbs_pdf = find_bbs_pdf(dwg)
        if bbs_pdf is None:  # worktree DRAWINGS may lack the BBS docs
            alt = Path("/Users/jonathan/elco/vme/DRAWINGS") / dwg.name
            bbs_pdf = find_bbs_pdf(alt) if alt.exists() else None
        bbs = parse_bbs_pdf(bbs_pdf) if bbs_pdf else None
        if bbs:
            L.append(f"\n### RECONCILIATION vs ITEMIZED BBS ({bbs_pdf.name})"
                     " — row by row")
            L += match_bbs_rows(bbs, d["bars"])
            bbs_tot = sum(r.weight_kg for r in bbs)
            L.append(f"  BBS grand total {bbs_tot:.1f}kg"
                     f"  (Summary Schedule total"
                     f" {sum(r.weight_kg for r in summary):.1f}kg"
                     " — the two official docs disagree)" if summary else "")
    return L


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("drawings", nargs="?", default="../DRAWINGS")
    ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    ddir, out_dir = Path(args.drawings), Path(args.out)
    dwgs = sorted(ddir.glob("*.dwg"))
    L = [f"# FULL DWG INVENTORY — {len(dwgs)} files from {ddir}"]
    for dwg in dwgs:
        L += panel_report(dwg, out_dir)
    report = "\n".join(L)
    rp = Path(args.report) if args.report else out_dir / "FULL_INVENTORY.txt"
    rp.write_text(report)
    print(report)
    print(f"\n[written to {rp}]")


if __name__ == "__main__":
    main()
