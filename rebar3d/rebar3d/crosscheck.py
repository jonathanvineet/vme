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

_COUNT_RE = re.compile(r"\(?(\d+)\)?\s*-\s*\(?T(\d+)\)?\b")
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


_MARK_LABEL_RE = re.compile(r"^[A-Z]\d{0,2}$")


@dataclass
class MarkGroup:
    mark: str
    diameter: int
    total_count: int
    instances: list[Callout]  # every raw callout instance found paired to this mark


def parse_letter_marks(ents: list[Ent], views=None, pair_dist: float = 250.0,
                       same_view_dist: float = 500.0) -> list[MarkGroup]:
    """Pair every schedule-mark letter label ("B", "D", "D1", "G", ...) with
    the nearest count callout, then aggregate each mark's TRUE total count
    across every place the label appears on the sheet.

    Worked out by hand on PW-01 this session before being generalized here:
    a shop drawing repeats the same label in multiple views for the
    reader's convenience (an elevation-side detail also labelled in a
    section cut) — those repeats must NOT be summed, or a real family gets
    inflated by however many views happen to show it. But a single view
    can ALSO legitimately show the same letter twice for two genuinely
    different physical instances of the same mark (PW-01's mark "D": two
    separate corner instances, "-(3)-T8" at each end of one section view,
    that really do need summing to reach the true total of 6). The
    distinguishing signal is view membership + spatial separation, not the
    letter alone: two same-letter callouts in the SAME view cluster more
    than `same_view_dist` apart are treated as distinct real instances
    (summed); the same letter appearing again in a DIFFERENT view is
    treated as a repeated re-label of what's already counted (deduped via
    max, not summed). Verified exactly on PW-01: "D" labels both the
    "-(14)-T8" callout (repeated identically in 3 different views -> 14,
    not 42) and two separate "-(3)-T8" instances within one view (3+3=6,
    not 3) -- combined total 20, exactly matching the official D+D1
    combined count (this DWG's own drafting doesn't distinguish D from D1
    at all; that split only exists in the separate office schedule).

    `views`: pre-clustered `View` list (see `views.cluster_views`) giving
    real view membership; if not supplied, clusters `ents` itself.
    """
    if views is None:
        from .views import cluster_views
        views = cluster_views(ents)

    # `cluster_views`' own margin-based clustering can merge a view's real
    # geometry with far-flung annotation entities that happen to chain-
    # connect to it (confirmed on PW-01: view 0's raw entity bbox came out
    # 5563-10205 -- 3600mm wider than the elevation's own real 6522-9272
    # panel outline -- swallowing a *different* callout instance 4500mm+
    # away and wrongly summing it as if it were a distinct in-view
    # instance). Use each view's real wall/section-band outline (from
    # `wall_outline`, the same tight boundary the rest of the pipeline
    # trusts) instead of the raw entity bbox wherever one exists.
    from .extract import wall_outline
    view_bounds = []
    for v in views:
        try:
            bbox, _ = wall_outline(v.ents)
            view_bounds.append(bbox)
        except (ValueError, IndexError):
            view_bounds.append(None)

    def view_of(x: float, y: float, margin: float = 600.0) -> int:
        for i, bbox in enumerate(view_bounds):
            if bbox is None:
                continue
            bx0, by0, bx1, by1 = bbox
            if bx0 - margin <= x <= bx1 + margin and by0 - margin <= y <= by1 + margin:
                return i
        return -1  # no confident view membership -- treated as its own group

    callouts = parse_count_callouts(ents)
    used = [False] * len(callouts)
    labels = [e for e in ents if e.kind in ("TEXT", "MTEXT")
             and _MARK_LABEL_RE.match((e.text or "").strip())]

    raw: dict[str, list[tuple[int, Callout]]] = {}  # mark -> [(view_idx, callout)]
    for e in labels:
        text = (e.text or "").strip()
        lx, ly = (e.bbox[0] + e.bbox[2]) / 2, (e.bbox[1] + e.bbox[3]) / 2
        best_i, best_d = None, pair_dist
        for i, c in enumerate(callouts):
            if used[i]:
                continue
            d = math.dist((lx, ly), (c.x, c.y))
            if d < best_d:
                best_d, best_i = d, i
        if best_i is None:
            continue
        used[best_i] = True
        c = callouts[best_i]
        raw.setdefault(text, []).append((view_of(c.x, c.y), c))

    groups = []
    next_singleton = -2  # -1 itself is reserved below for "no confident view"
    for mark, items in raw.items():
        by_view: dict[int, list[Callout]] = {}
        for vi, c in items:
            # -1 ("no confident view membership") must NOT pool unrelated
            # instances together under one shared bucket -- each gets its
            # own singleton group instead, so distant same-letter repeats
            # with no resolvable view (confirmed on PW-01's mark "C": all
            # 3 instances fall outside every section's own wall-outline
            # bbox) are correctly deduped via max(), not summed.
            if vi == -1:
                by_view[next_singleton] = [c]
                next_singleton -= 1
            else:
                by_view.setdefault(vi, []).append(c)
        per_view_totals = []
        for vi, cs in by_view.items():
            # within one view: distinct positions (>same_view_dist apart)
            # are genuinely different instances and get summed; near-
            # duplicates (same detail, jittered label placement) don't.
            kept: list[Callout] = []
            for c in cs:
                if any(math.dist((c.x, c.y), (k.x, k.y)) < same_view_dist for k in kept):
                    continue
                kept.append(c)
            per_view_totals.append(sum(k.count for k in kept))
        total = max(per_view_totals) if per_view_totals else 0
        dia = items[0][1].diameter
        groups.append(MarkGroup(mark, dia, total, [c for _, c in items]))
    return groups


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


def mark_report(groups: list[MarkGroup], bars3d, x0: float = 0.0, y0: float = 0.0,
                radius: float = 1800.0) -> str:
    """Per schedule-mark-letter reconciliation: `parse_letter_marks`'s true
    deduped total vs how many reconstructed bars of that diameter sit near
    any of the mark's real callout positions -- the same drawing-wide,
    per-instance radius check `cross_check` does for raw callouts, but
    against the letter-aggregated true count instead of a possibly-
    repeated single instance's own number.

    `bars3d` (`panel.bars`) is already offset into the panel's own local
    coordinate frame; callout positions are raw DWG coordinates, so `x0,y0`
    (the same offset `reconstruct_panel` applied) must be subtracted before
    comparing the two -- confirmed the hard way: skipping this made every
    single mark read "found=0" despite the bars genuinely being there.
    """
    lines = [f"{'mark':<8}{'dia':<6}{'expected':>9}{'found':>7}  status  instances"]
    for g in sorted(groups, key=lambda g: g.mark):
        near = set()
        for c in g.instances:
            cx, cy = c.x - x0, c.y - y0
            for i, b in enumerate(bars3d):
                if b.diameter != g.diameter:
                    continue
                d = min(math.dist((p[0], p[1]), (cx, cy)) for p in b.points)
                if d <= radius:
                    near.add(i)
        found = len(near)
        gap = found - g.total_count
        status = "OK" if gap == 0 else ("SHORT" if gap < 0 else "OVER")
        lines.append(f"{g.mark:<8}T{g.diameter:<5}{g.total_count:>9}{found:>7}  "
                     f"{status:<6}  {len(g.instances)}")
    return "\n".join(lines)


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
