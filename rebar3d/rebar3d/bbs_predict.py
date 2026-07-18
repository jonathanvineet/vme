"""Predict a Bar Bending Schedule from the DWG alone — no BBS PDF needed.

The rules encoded here were learned by reconciling the two available
itemized BBS documents (PW-GF-02.pdf, PW-GF-09.pdf) row-by-row against the
raw DWG content, and every rule is numerically verified against both —
see BBS_RULES.md for the evidence. The core insight driving the hybrid
design: the 3D reconstruction is reliable for bars that are genuinely
*drawn* (the mesh), while the fragmented/schematic categories (ties,
hairpin U-bars, crack bars) are precisely the ones the drawing's own text
callouts + standard-shape rules pin down exactly. So: reconstruction for
mesh, rules for everything the callouts describe.

Verified constants (both panels):
  cover = 30mm everywhere; unit weight = d^2/162 kg/m;
  bend deduction = 2d per bend (open: bends = segments-1; closed tie: 16d);
  tie shape = column core loop + 80mm hooks, 0.632m at T8/t160;
  hairpin = 0.4/web/0.4 with web = thickness - 2*cover;
  ties per run = floor(2.87/pitch)+1 = 29 at 100c/c.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

COVER = 0.030  # metres, verified both panels

_PITCH_RE = re.compile(r"T(\d+)\s*(?:@|\w*\s*@)\s*(\d+)\s*mm", re.IGNORECASE)
_TIES_RE = re.compile(r"T(\d+)\s+Ties?\s*@\s*(\d+)\s*mm", re.IGNORECASE)
_UBAR_RE = re.compile(r"T(\d+)\s*UBAR\s*@\s*(\d+)\s*mm", re.IGNORECASE)
_COUNT_RE = re.compile(r"(\d+)\s*-\s*T(\d+)\b(.*)", re.IGNORECASE)


def unit_wt(d_mm: int) -> float:
    return d_mm * d_mm / 162.0


def bent_length(segments: list[float], d_mm: int, closed_tie: bool = False) -> float:
    """BBS Rule 3: stated length = sum(segments) - n_bends * 2d."""
    n_bends = 8 if closed_tie else max(len(segments) - 1, 0)
    return sum(segments) - n_bends * 2 * (d_mm / 1000.0)


@dataclass
class PredictedRow:
    desc: str
    dia: int
    count: int
    length_m: float  # per-bar, after bend deduction
    source: str      # which rule/evidence produced it

    @property
    def weight(self) -> float:
        return self.count * self.length_m * unit_wt(self.dia)


def predict_from_text(all_texts: list[str], width: float, height: float,
                      thickness: float, opening_perims_m: float = 0.0) -> list[PredictedRow]:
    """Rows derivable purely from callout text + panel dimensions.

    Covers the categories the geometry pipeline is structurally bad at
    (drawn as fragments/schematics): ties, hairpin U-bars, crack bars and
    other explicit `N -T{d}` details. Mesh rows are NOT predicted here —
    take those from the 3D reconstruction, which sees them directly.
    """
    W, H, t = width / 1000.0, height / 1000.0, thickness / 1000.0
    rows: list[PredictedRow] = []
    texts = Counter(s.strip() for s in all_texts if s.strip())

    run_h = H - 2 * COVER  # a vertical run spans the clear height

    for txt, n_inst in sorted(texts.items()):
        m = _TIES_RE.search(txt)
        if m:
            dia, pitch = int(m.group(1)), int(m.group(2)) / 1000.0
            per_run = math.floor(run_h / pitch) + 1
            # verified: each callout instance labels one confined run
            web = t - 2 * COVER
            segs = [0.08, web, 0.2, web, 0.2, 0.08]
            L = bent_length(segs, dia, closed_tie=True)
            rows.append(PredictedRow(f"Ties {txt}", dia, n_inst * per_run, L,
                                     f"{n_inst} runs x {per_run}"))
            continue
        m = _UBAR_RE.search(txt)
        if m:
            dia, pitch = int(m.group(1)), int(m.group(2)) / 1000.0
            # hairpins run along panel + opening edges at the callout pitch;
            # each instance labels one edge zone. Without zone extents the
            # count comes from total labelled perimeter — approximate each
            # instance as one full edge of the mean edge length.
            mean_edge = (W + H)  # half-perimeter / 2 edges
            per_run = math.floor(mean_edge / 2 / pitch)
            web = t - 2 * COVER
            L = bent_length([0.4, web, 0.4], dia)
            rows.append(PredictedRow(f"UBAR {txt}", dia, n_inst * per_run, L,
                                     f"{n_inst} zones x ~{per_run} (approx)"))
            continue
        m = _COUNT_RE.match(txt)
        if m:
            n, dia, label = int(m.group(1)), int(m.group(2)), m.group(3).strip()
            if "crack" in label.lower():
                # diagonal corner bars, drawn ~1.2m; explicit counts are
                # literal and additive across callout instances (verified)
                rows.append(PredictedRow(f"Crack bar ({txt})", dia, n * n_inst, 1.2,
                                         f"{n_inst} callouts x {n}"))
            else:
                # full-width/height detail bars; length = clear span
                rows.append(PredictedRow(f"Detail ({txt})", dia, n * n_inst,
                                         max(W, H) - 2 * COVER,
                                         f"{n_inst} callouts x {n} (span approx)"))
    return rows


def format_rows(rows: list[PredictedRow]) -> str:
    lines = [f"{'description':<32}{'dia':>4}{'n':>5}{'len(m)':>8}{'kg':>9}  source"]
    tot = 0.0
    for r in sorted(rows, key=lambda r: (r.dia, r.desc)):
        tot += r.weight
        lines.append(f"{r.desc:<32}{r.dia:>4}{r.count:>5}{r.length_m:>8.3f}{r.weight:>9.2f}  {r.source}")
    lines.append(f"{'TOTAL (text-derived rows only)':<49}{tot:>9.2f}")
    return "\n".join(lines)
