"""Read the drawing's own bar schedule from its companion PDF, for calibration.

Every (R) sheet in this drawing set prints a "Summary Schedule" table (per-
diameter total length + weight) at the bottom — the shop drawing's own
authoritative bar count, independent of how well the 2D linework geometry
reconstructs.
"""
from __future__ import annotations

import re
from pathlib import Path


def pdf_summary_schedule(pdf_path: Path) -> dict[int, tuple[float, float]]:
    """{diameter: (total_length_mm, weight_kg)} parsed from the PDF's table."""
    import pypdf

    text = pypdf.PdfReader(str(pdf_path)).pages[0].extract_text()
    m0 = re.search(r"Summary\s+Schedule", text)
    if not m0:
        return {}
    block = text[m0.end():m0.end() + 800]
    out: dict[int, tuple[float, float]] = {}
    for m in re.finditer(r"(\d+)\s*mm\s+(\d+)\s*mm\s+([\d.]+)\s*kg", block):
        d, length, w = int(m.group(1)), float(m.group(2)), float(m.group(3))
        out[d] = (length, w)
    return out


def pdf_bbs_schedule(pdf_path: Path) -> dict[int, tuple[float, float]]:
    """{diameter: (total_length_mm, weight_kg)} from a full Bar Bending
    Schedule PDF — one row per bar shape (spacing, dia, count, per-bar
    length, total length, unit weight, total weight). This is a finer,
    independently-authored document (separate from the (R) sheet's own
    "Summary Schedule" table) and is preferred as calibration ground truth
    when both exist, since it itemises every bar shape rather than just a
    per-diameter roll-up."""
    import pypdf

    text = pypdf.PdfReader(str(pdf_path)).pages[0].extract_text()
    out: dict[int, list[float]] = {}
    # one row per line: SNo, "Horizontal"/"Vertical", "Bar", spacing-or-"-",
    # dia, count, up to 6 dims (numbers or "-"), length, total-length,
    # unit-wt, total-wt — trailing fields are always numeric.
    line_re = re.compile(r"^\d+\s+(?:Horizontal|Vertical)\s+Bar\s+\S+\s+(\d+)\s+(\d+)\s+(.+)$")
    for line in text.splitlines():
        m = line_re.match(line.strip())
        if not m:
            continue
        d = int(m.group(1))
        nums = [t for t in m.group(3).split() if t != "-"]
        if len(nums) < 4:
            continue
        total_len_m, total_wt = float(nums[-3]), float(nums[-1])
        length, weight = out.setdefault(d, [0.0, 0.0])
        out[d] = [length + total_len_m * 1000.0, weight + total_wt]
    return {d: (v[0], v[1]) for d, v in out.items()}


def find_schedule_pdf(dwg_path: Path) -> Path | None:
    """The matching Summary-Schedule PDF sits alongside the DWG — sometimes
    with a stray space before the extension (an export quirk in this
    drawing set)."""
    stem = dwg_path.stem.replace(" ", "")
    for cand in dwg_path.parent.glob("*.pdf"):
        if cand.stem.replace(" ", "") == stem:
            return cand
    return None


def find_bbs_pdf(dwg_path: Path) -> Path | None:
    """The full Bar Bending Schedule, filed under the bare panel name with
    no "(R)"/"(M...)" suffix, e.g. "PW-GF-02(R).dwg" -> "PW-GF-02.pdf"."""
    base = dwg_path.stem.split("(")[0].strip()
    cand = dwg_path.parent / f"{base}.pdf"
    return cand if cand.exists() else None


def find_schedule(dwg_path: Path) -> dict[int, tuple[float, float]]:
    """Best available bar schedule for this drawing: prefer the itemised
    BBS PDF over the (R) sheet's coarser Summary Schedule table."""
    bbs = find_bbs_pdf(dwg_path)
    if bbs:
        sched = pdf_bbs_schedule(bbs)
        if sched:
            return sched
    pdf = find_schedule_pdf(dwg_path)
    return pdf_summary_schedule(pdf) if pdf else {}
