"""Cross-check reconstructed bars against the drawing's own count callouts.

Shop drawings label local reinforcement details directly — "6 -T12",
"2 -T10 -Crack Bar", "2 -T12 Perimeter Bar" — stating exactly how many bars
of what diameter belong to that detail. The reconstruction pipeline never
reads this text; it re-derives bar counts purely from double-line geometry
and section circles, which is exactly where the accuracy gaps traced
elsewhere in this project (missing bars, fabricated diameters, depth
mis-matches) come from. This module doesn't feed the callouts into
reconstruction — it independently re-counts what geometry-based
reconstruction actually produced near each callout's position and reports
the two side by side, so a mismatch is visible and attributable to a
specific, real, labelled detail instead of only showing up as a fuzzy
aggregate weight gap.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .extract import Bar2D, snap_diameter
from .loader import Ent

_COUNT_RE = re.compile(r"\(?(\d+)\)?\s*-\s*T(\d+)\b")
_ANY_DIA_RE = re.compile(r"\bT(\d+)\b")


@dataclass
class Callout:
    count: int
    diameter: int
    x: float
    y: float
    text: str


def parse_count_callouts(ents: list[Ent]) -> list[Callout]:
    """Every "N -T{d}" style label ("6 -T12", "2 -T10 -Crack Bar", ...).

    Deliberately narrow: only the explicit-count style, not pitch callouts
    ("T8 @150 mm") — a pitch alone doesn't state a count without also
    knowing the run's length, so it isn't a clean apples-to-apples check
    the way "N -T{d}" is.
    """
    out = []
    for e in ents:
        if e.kind not in ("TEXT", "MTEXT"):
            continue
        m = _COUNT_RE.search(e.text or "")
        if not m:
            continue
        cx = (e.bbox[0] + e.bbox[2]) / 2
        cy = (e.bbox[1] + e.bbox[3]) / 2
        out.append(Callout(int(m.group(1)), int(m.group(2)), cx, cy, e.text.strip()))
    return out


def text_callout_diameters(ents: list[Ent]) -> set[int]:
    """Every bar diameter ("T8", "T20", ...) mentioned anywhere in the
    sheet's own text/pitch/count callouts.

    Used as a ground-truth diameter set for phantom-bar suppression on
    panels that carry no Summary Schedule at all (no paper-space table, no
    sibling PDF) -- e.g. a drawing whose text only ever says "T8" and
    "T10" has no business reconstructing T12/T16/T20 bars; those diameters
    can only come from generic-mesh rail mis-pairing.
    """
    out: set[int] = set()
    for e in ents:
        if e.kind not in ("TEXT", "MTEXT"):
            continue
        for m in _ANY_DIA_RE.finditer(e.text or ""):
            out.add(int(m.group(1)))
    return out


@dataclass
class CrossCheckResult:
    callout: Callout
    found: int
    nearest_dist: float | None


def cross_check(callouts: list[Callout], bars2d: list[Bar2D], radius: float = 1800.0) -> list[CrossCheckResult]:
    """For each callout, how many reconstructed bars of that diameter sit
    within `radius` of the label. Distinct 2D bar *positions* are counted,
    not the z-expanded 3D bar list, so a front+back mesh pair on a bar the
    reconstruction already found the depth for doesn't double-count.

    `radius` covers the observed leader/label-to-geometry offset. Widened
    800->1800mm after PW-45 showed 5 of 6 "SHORT" results were false
    negatives purely from label offset (826-1698mm — the real bar existed,
    just past the old radius; only 1 of the 6 had genuinely no matching-
    diameter geometry anywhere in its own view). A SHORT result is only
    trustworthy evidence of a real gap when nothing of that diameter shows
    up anywhere nearby at all, so a false SHORT is a much worse failure
    mode here than a slightly noisier OVER count — this isn't precise
    bar-to-label registration, it's a coarse sanity check. Read SHORT
    results as trustworthy; OVER results are inherently noisy whenever
    labels cluster close together, since each one's search radius also
    picks up bars that really belong to its neighbour's count (worse now
    at 1800mm than at 800mm — treat OVER purely as noise, never evidence).
    """
    results = []
    for c in callouts:
        near = 0
        best = None
        for b in bars2d:
            if snap_diameter(b.diameter) != c.diameter:
                continue
            # nearest distance from the callout to any point on the bar, not
            # just its midpoint — a callout for a tall vertical bar's local
            # detail typically sits level with one *end* of it, not the middle
            d = min(math.dist(p, (c.x, c.y)) for p in b.points)
            if d <= radius:
                near += 1
                if best is None or d < best:
                    best = d
        results.append(CrossCheckResult(c, near, best))
    return results


def format_report(results: list[CrossCheckResult]) -> str:
    lines = [f"{'callout':<28} {'expected':>8} {'found':>6} {'nearest':>9}  status"]
    for r in sorted(results, key=lambda r: r.found - r.callout.count):
        gap = r.found - r.callout.count
        status = "OK" if gap == 0 else ("SHORT" if gap < 0 else "OVER")
        dist = f"{r.nearest_dist:.0f}mm" if r.nearest_dist is not None else "-"
        lines.append(
            f"{r.callout.text:<28} {r.callout.count:>8} {r.found:>6} {dist:>9}  {status}"
        )
    return "\n".join(lines)
