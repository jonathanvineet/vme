"""Extract and compare against the drawing's own printed "Summary Schedule".

The (R) sheet's Summary Schedule table (per-diameter total bar length +
weight) is ground truth: it's what the drawing itself declares, produced
from the live Revit model, independent of how well this pipeline's
geometry-only reconstruction manages to re-derive the same numbers. 3D
reconstruction accuracy is a long tail of individually distinct geometric
edge cases (confirmed repeatedly: fabricated diameters, depth mismatches,
bars invisible to double-line pairing, bars only in a detail view) that
won't all close quickly. Surfacing the schedule directly, alongside
whatever the reconstruction currently produces, gives an always-accurate
weight number without waiting on that reconstruction work to finish.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScheduleRow:
    diameter: int
    length_mm: float
    weight_kg: float


def extract_schedule(pdf_path: Path) -> list[ScheduleRow] | None:
    """Parse the Summary Schedule table off the first page of an (R) PDF.

    Returns None if the PDF has no such table (not every panel's sheet
    carries one, e.g. mould-only sheets).
    """
    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    text = reader.pages[0].extract_text()
    idx = text.find("Summary Schedule")
    if idx < 0:
        return None
    rows = [
        ScheduleRow(int(m.group(1)), float(m.group(2)), float(m.group(3)))
        for m in re.finditer(r"(\d+)\s*mm\s+([\d.]+)\s*mm\s+([\d.]+)\s*kg", text[idx:])
    ]
    return rows or None


def find_schedule_pdf(dwg_path: Path) -> Path | None:
    """The (R) PDF beside a given (R) DWG, tolerating a stray space before
    the extension seen in this drawing set (e.g. "PW-GF-02(R) .pdf")."""
    for p in dwg_path.parent.glob(f"{dwg_path.stem}*.pdf"):
        return p
    return None


def compare_to_bars(rows: list[ScheduleRow], bars) -> str:
    """Side-by-side official vs. reconstructed weight, per diameter."""
    import math

    def poly_len(pts):
        return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))

    found: dict[int, float] = {}
    for b in bars:
        found[b.diameter] = found.get(b.diameter, 0.0) + poly_len(b.points)

    official = {r.diameter: r.weight_kg for r in rows}
    all_dia = sorted(set(found) | set(official))
    lines = [f"{'bar':>5} {'reconstructed':>13} {'official':>10} {'gap':>8} {'%':>6}"]
    tot_f = tot_o = 0.0
    for dia in all_dia:
        wf = (found.get(dia, 0.0) / 1000) * dia * dia / 162
        wo = official.get(dia, 0.0)
        tot_f += wf
        tot_o += wo
        pct = f"{100 * wf / wo:.0f}%" if wo else ("extra" if wf else "-")
        lines.append(f"T{dia:<4} {wf:>12.2f}k {wo:>9.2f}k {wf - wo:>+7.2f}k {pct:>6}")
    tot_pct = f"{100 * tot_f / tot_o:.0f}%" if tot_o else "-"
    lines.append(f"{'TOTAL':>5} {tot_f:>12.2f}k {tot_o:>9.2f}k {tot_f - tot_o:>+7.2f}k {tot_pct:>6}")
    return "\n".join(lines)
