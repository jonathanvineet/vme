"""Compose elevation + sections into a 3D rebar model.

Panel coordinate frame:
  X = along panel length (elevation horizontal), origin at panel left
  Y = panel height (elevation vertical), origin at panel bottom
  Z = through thickness, origin at one face (0..thickness)

Depth (Z) recovery: section views cut the panel and draw crossing bars as
circles. A "horizontal" section (width ≈ panel width) shows vertical bars
as circles whose X registers to elevation X and whose Y-offset inside the
cut wall outline is the bar's Z. A "vertical" section (height ≈ panel
height) does the same for horizontal bars.
"""
from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field

from .extract import Bar2D, extract_bars, snap_diameter, wall_outline
from .views import View

AXIS_TOL = math.radians(3)


@dataclass
class Bar3D:
    points: list[tuple[float, float, float]]
    diameter: int
    kind: str  # v-mesh | h-mesh | diagonal | shape | u-bar | face-dowel | link
    z_source: str  # section | default


@dataclass
class Feature:
    """A non-rebar element cast into the panel.

    kind: corbel (concrete nib), embed (steel section), anchor (lifting
    spread anchor), loop (wire loop box), sleeve (corrugated pipe /
    through-thickness duct).
    """

    kind: str
    box: tuple[float, float, float, float, float, float] | None = None  # x0,y0,z0,x1,y1,z1
    center: tuple[float, float] | None = None  # sleeve position on the face
    radius: float = 0.0  # sleeve inner radius
    label: str = ""


@dataclass
class Panel:
    name: str
    width: float
    height: float
    thickness: float
    openings: list[list[tuple[float, float]]]
    bars: list[Bar3D]
    stats: dict = field(default_factory=dict)
    families: list[dict] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)


def mesh_families(bars: list[Bar3D], tol_z: float = 8.0) -> list[dict]:
    """Group mesh bars by orientation/diameter/depth and measure their spacing."""
    groups: dict[tuple[str, int, float], list[float]] = {}
    for b in bars:
        if b.kind not in ("v-mesh", "h-mesh"):
            continue
        z = b.points[0][2]
        pos = b.points[0][0] if b.kind == "v-mesh" else b.points[0][1]
        placed = False
        for (kind, dia, gz) in list(groups):
            if kind == b.kind and dia == b.diameter and abs(gz - z) <= tol_z:
                groups[(kind, dia, gz)].append(pos)
                placed = True
                break
        if not placed:
            groups[(b.kind, b.diameter, z)] = [pos]

    fams = []
    for (kind, dia, z), poss in sorted(groups.items()):
        poss.sort()
        diffs = [b - a for a, b in zip(poss, poss[1:]) if 20 < b - a < 600]
        spacing = None
        if diffs:
            counts: dict[int, int] = {}
            for d in diffs:
                key = int(round(d / 5.0) * 5)
                counts[key] = counts.get(key, 0) + 1
            spacing = max(counts, key=lambda k: counts[k])
        fams.append({
            "kind": kind, "d": dia, "z": round(z, 1), "count": len(poss),
            "spacing": spacing,
        })
    return [f for f in fams if f["count"] >= 2]


def _orientation(b: Bar2D) -> str:
    (x0, y0), (x1, y1) = b.points[0], b.points[-1]
    ang = math.atan2(y1 - y0, x1 - x0) % math.pi
    if len(b.points) > 2:
        return "shape"
    if ang < AXIS_TOL or math.pi - ang < AXIS_TOL:
        return "h"
    if abs(ang - math.pi / 2) < AXIS_TOL:
        return "v"
    return "diag"


@dataclass
class SectionInfo:
    role: str  # "horizontal" (cuts vertical bars) or "vertical"
    wall_bbox: tuple[float, float, float, float]
    thickness: float
    # circles: (coordinate along panel axis in section frame, z-offset, radius)
    circles: list[tuple[float, float, float]]
    # face-protruding bar profiles: (pos along panel axis, z0, z1, dia);
    # z outside [0, thickness] means the bar sticks out of that face
    prot: list[tuple[float, float, float, float]]
    # in-cut bar layers: (z, dia) of bars drawn along the section's long axis
    layers: list[tuple[float, float]]
    drawn_x: bool = True  # section long axis drawn along sheet X
    view: "View | None" = None
    # U-bar bend profiles seen in the cut: (pos, z_a, z_b, sgn, dia) — a bar
    # wrapping an edge at panel-axis coordinate `pos`, joining depths z_a/z_b,
    # apex pointing in `sgn` direction along the axis
    ubars: list[tuple[float, float, float, float, float]] = field(default_factory=list)


def classify_sections(
    views: list[View], panel_w: float, panel_h: float,
    elev_bbox: tuple[float, float, float, float] | None = None,
) -> list[SectionInfo]:
    infos: list[SectionInfo] = []
    for v in views[1:]:
        wall = [e for e in v.ents if e.layer.startswith("A-WALL")]
        if not wall:
            wall = [e for e in v.ents if e.layer.startswith("A-FLOR")]
        if not wall:
            wall = [e for e in v.ents if e.layer.startswith("S-COLS")]
        if not wall:
            continue
        xs, ys = [], []
        for e in wall:
            b = e.bbox
            xs += [b[0], b[2]]
            ys += [b[1], b[3]]
        wb = (min(xs), min(ys), max(xs), max(ys))
        w, h = wb[2] - wb[0], wb[3] - wb[1]
        # A section's long axis spans one panel dimension regardless of how
        # the view is laid out on the sheet; the short axis is the thickness.
        long_len, thickness = max(w, h), min(w, h)
        drawn_x = w >= h  # long axis drawn along sheet X
        if thickness > 0.5 * min(panel_w, panel_h):
            continue
        origin_long = wb[0] if drawn_x else wb[1]
        if abs(long_len - panel_w) < 0.08 * panel_w:
            role = "horizontal"  # cuts vertical elevation bars
        elif abs(long_len - panel_h) < 0.08 * panel_h:
            role = "vertical"  # cuts horizontal elevation bars
        elif elev_bbox is not None:
            # Partial section (the cut wall band is interrupted by openings /
            # corbels). Revit lays sections out sharing the elevation's
            # coordinate along the panel axis, so register by that instead.
            ex0, ey0, ex1, ey1 = elev_bbox
            lo = wb[1] if not drawn_x else wb[0]
            hi = wb[3] if not drawn_x else wb[2]
            if not drawn_x and ey0 - 50 <= lo and hi <= ey1 + 50:
                role = "vertical"
                origin_long = ey0
            elif drawn_x and ex0 - 50 <= lo and hi <= ex1 + 50:
                role = "horizontal"
                origin_long = ex0
            else:
                continue
        else:
            continue

        def to_section(px: float, py: float) -> tuple[float, float]:
            """Map drawing coords to (pos along panel axis, z in thickness)."""
            if drawn_x:
                return px - origin_long, py - wb[1]
            return py - origin_long, px - wb[0]

        circles = []
        raw_prot = []  # (pos, z_lo, z_hi) per outline line
        for e in v.ents:
            if e.layer != "S-RBAR":
                continue
            if e.kind == "CIRCLE" and 2.0 <= e.radius <= 17.0:
                pos, z = to_section(*e.center)
                if -5 <= z <= thickness + 5:
                    circles.append((pos, z, e.radius))
            elif e.kind == "LINE":
                p0, z0 = to_section(*e.points[0])
                p1, z1 = to_section(*e.points[1])
                # protruding bars run along the thickness axis, past the face
                if abs(p0 - p1) < 3 and abs(z0 - z1) > 80:
                    lo, hi = min(z0, z1), max(z0, z1)
                    if lo < -60 or hi > thickness + 60:
                        raw_prot.append((p0, lo, hi))
        # pair the two outline lines of each protruding bar into a centerline
        prot = []
        raw_prot.sort()
        k = 0
        while k < len(raw_prot):
            if k + 1 < len(raw_prot) and 5.0 <= raw_prot[k + 1][0] - raw_prot[k][0] <= 34.0:
                a, b = raw_prot[k], raw_prot[k + 1]
                prot.append(((a[0] + b[0]) / 2, min(a[1], b[1]), max(a[2], b[2]), b[0] - a[0]))
                k += 2
            else:
                k += 1
        # bars drawn in the cut plane along the section's long axis reveal a
        # reinforcement layer's depth directly (e.g. the hooked top bar)
        layers: list[tuple[float, float]] = []
        cut_bars = extract_bars(v.ents, min_len=25.0)
        for b in cut_bars:
            best_len = 0.0
            best_z = None
            for i in range(len(b.points) - 1):
                (ax, ay), (bx2, by2) = b.points[i], b.points[i + 1]
                seg_len = math.dist((ax, ay), (bx2, by2))
                aligned = abs(by2 - ay) < 3 if drawn_x else abs(bx2 - ax) < 3
                if aligned and seg_len > 0.35 * long_len and seg_len > best_len:
                    _, z = to_section(ax, ay)
                    best_len, best_z = seg_len, z
            if best_z is not None and -30 <= best_z <= thickness + 30:
                layers.append((best_z, b.diameter))

        # U-bar bend profiles: a bar wrapping an edge between the two mesh
        # faces. Drawn either as a full U (two legs + bend) or — when the
        # legs are the mesh bars themselves — as just the bend: quarter-arcs
        # joined across the thickness, endpoints at the two leg depths.
        ubars: list[tuple[float, float, float, float, float]] = []
        for b in cut_bars:
            if len(b.points) < 4:
                continue
            sp = [to_section(px, py) for px, py in b.points]
            (p0, z0), (pn, zn) = sp[0], sp[-1]
            dz = abs(zn - z0)
            if not (25 <= dz <= thickness) or not (-15 <= z0 <= thickness + 15 and -15 <= zn <= thickness + 15):
                continue
            span = max(p for p, _ in sp) - min(p for p, _ in sp)
            end_mid = (p0 + pn) / 2
            if abs(p0 - pn) <= 20 and span <= 90:
                # bend-only wrap: apex is the point farthest from the leg tips
                apex = max((p for p, _ in sp), key=lambda p: abs(p - end_mid))
                sgn = 1.0 if apex > end_mid else -1.0
                ubars.append((end_mid, z0, zn, sgn, b.diameter))
            else:
                # full U: legs along the axis, bend at one extremum
                leg_a = abs(sp[1][0] - p0)
                leg_b = abs(sp[-2][0] - pn)
                if leg_a < 60 or leg_b < 60:
                    continue
                if abs(sp[1][1] - z0) > 6 or abs(sp[-2][1] - zn) > 6:
                    continue
                lo, hi = min(p0, pn), max(p0, pn)
                bend = [p for p, _ in sp[2:-2]] or [(sp[1][0] + sp[-2][0]) / 2]
                bmid = sum(bend) / len(bend)
                if bmid <= lo:
                    ubars.append((min(p for p, _ in sp), z0, zn, -1.0, b.diameter))
                elif bmid >= hi:
                    ubars.append((max(p for p, _ in sp), z0, zn, 1.0, b.diameter))

        infos.append(SectionInfo(role, wb, thickness, circles, prot, layers,
                                 drawn_x=drawn_x, view=v, ubars=ubars))
    return infos


def _detail_marker_pos(elev_ents, axis: int) -> list[tuple[float, str]]:
    """(position, title-number) candidates for a section cut-plane marker
    along `axis` (1=Y, for a horizontal section; 0=X, for a vertical one).

    A Revit section cut is drawn in the elevation as a pair of "Section
    Head"/"Section Tail" block instances sharing a position on the cut axis,
    labelled with a small standalone number text placed nearby — the same
    number printed as the detail view's own title elsewhere on the sheet.
    """
    groups: dict[int, list] = {}
    for e in elev_ents:
        if e.block and "Section" in e.block:
            groups.setdefault(e.bref, []).append(e)
    points = []
    for es in groups.values():
        pts = []
        for e in es:
            if e.kind in ("LINE", "LWPOLYLINE"):
                pts.extend(e.points)
            elif e.kind in ("CIRCLE", "ARC"):
                pts.append(e.center)
        if not pts:
            continue
        vals = [p[axis] for p in pts]
        v0, v1 = min(vals), max(vals)
        if v1 - v0 > 400:  # spans most of the panel: the cut's own long axis, not its position
            continue
        points.append((v0 + v1) / 2)
    points.sort()
    merged: list[float] = []
    for v in points:
        if merged and abs(v - merged[-1]) < 150:
            merged[-1] = (merged[-1] + v) / 2
        else:
            merged.append(v)
    out = []
    for v in merged:
        near = [e for e in elev_ents if e.kind in ("TEXT", "MTEXT") and e.text
                and e.text.strip().isdigit() and len(e.text.strip()) <= 2
                and abs((e.bbox[axis] + e.bbox[axis + 2]) / 2 - v) < 400]
        if near:
            out.append((v, near[0].text.strip()))
    return out


def _local_section_bars(views: list[View], sections: list[SectionInfo], elev: View,
                        bbox, allowed: set[int]) -> list[Bar3D]:
    """Recover bars drawn only inside a local section/detail cut, never as
    elevation double-line geometry the normal pairing path reads — seen on
    this drawing set for corbel cages and similar local reinforcement that
    the sheet's own "REFER FOR INDIVIDUAL MOULD DRAWING" convention doesn't
    fully dimension anywhere else.

    A qualifying section's along-axis coordinate already maps 1:1 onto the
    real panel axis (X for a horizontal section, Y for a vertical one) —
    the same registration `classify_sections` already trusts for its own
    circle/z-lookup matching. Candidates are restricted to genuinely local
    shapes (small span along that axis, or a bent/looped outline) so an
    already-counted full-span mesh member lying in the cut plane never gets
    double-added. The cross-axis position (the one coordinate the section
    itself can't show) is resolved via `_detail_marker_pos`, matched by
    elimination against which detail view already displays that marker's
    own title number internally.
    """
    x0, y0 = bbox[0], bbox[1]

    def tag_in(view: View, tag: str) -> bool:
        return any(e.kind in ("TEXT", "MTEXT") and e.text and e.text.strip() == tag
                   for e in view.ents)

    y_markers = _detail_marker_pos(elev.ents, axis=1)
    x_markers = _detail_marker_pos(elev.ents, axis=0)
    barmark_re = re.compile(r"^[A-Z]1?$")
    out: list[Bar3D] = []
    for s in sections:
        if s.view is None:
            continue
        # A bar-mark *key* table lists several distinct single-letter
        # references (A, B, B1, C, D, ...), each its own standalone text
        # entity, tying a letter to a bar type elsewhere on the sheet —
        # that's a legend of alternative shapes, not one real zone, and
        # gets rejected outright. A real local/edge zone (corbel cage, tie
        # column) instead states its counts and spacing directly in the
        # text ("3 -T8 TIES", "T8 Ties @100 mm", "6 -T12") with no
        # separate letter-reference token, however dense the pattern.
        marks = {e.text.strip() for e in s.view.ents if e.kind in ("TEXT", "MTEXT")
                 and e.text and barmark_re.match(e.text.strip())}
        if len(marks) >= 3:
            continue
        markers = y_markers if s.role == "horizontal" else x_markers
        candidates = [
            v for v, tag in markers
            if not tag_in(s.view, tag)
            and not any(v2 is not s.view and v2 is not elev and tag_in(v2, tag) for v2 in views)
        ]
        if not candidates:
            continue
        cross = candidates[0] - (y0 if s.role == "horizontal" else x0)
        wb = s.wall_bbox
        origin = wb[0] if s.drawn_x else wb[1]
        section_bars: list[Bar3D] = []
        for b in extract_bars(s.view.ents, min_len=15.0):
            dia = snap_diameter(b.diameter)
            if allowed and dia not in allowed:
                continue
            local = [
                (px - origin, py - wb[1]) if s.drawn_x else (py - origin, px - wb[0])
                for px, py in b.points
            ]
            span = max(p for p, _ in local) - min(p for p, _ in local)
            if span > 200:
                # a real local feature (corbel leg, tie, dowel) is small
                # along the section's own axis; anything spanning this much
                # is either an already-counted mesh/rail member lying in
                # the cut plane, or a spacing-callout/legend symbol
                # (repeating hatch marks) misread as one long bent bar —
                # neither belongs here.
                continue
            pts3 = [
                (pos, cross, z) if s.role == "horizontal" else (cross, pos, z)
                for pos, z in local
            ]
            section_bars.append(Bar3D(pts3, dia, "detail-bar", "detail"))
        # A dense confinement/tie zone can legitimately run the panel's
        # full height at a tight pitch (dozens of real ties) — only guard
        # against a runaway/degenerate extraction, not against density.
        if len(section_bars) > 150:
            continue
        # The zone's own pitch callout ("T8 Ties @100 mm") is ground truth
        # for how many bars really exist across the span the real detected
        # ones already establish — double-line pairing of a dense hatch
        # pattern routinely misses some strokes, the same occlusion problem
        # `_densify_families` solves for the main mesh, just scoped here to
        # this one local zone's own detected span instead of the whole
        # panel.
        pos_idx = 0 if s.role == "horizontal" else 1
        section_bars.extend(_densify_section_bars(
            section_bars, announced_spacings([s.view]), pos_idx))
        out.extend(section_bars)
    return out


def _densify_section_bars(section_bars: list[Bar3D], spacings: dict[int, set[int]],
                          pos_idx: int) -> list[Bar3D]:
    """`_densify_families`, scoped to one local-detail zone's own detected
    bars instead of the whole-panel mesh (see `_local_section_bars`). Ties
    from the same physical layer of a hatch-tick pattern land with more
    z-noise per instance than a clean double-line mesh bar does, so this
    buckets depth coarser (50mm, vs. 8mm for the main-mesh pass)."""
    groups: dict[tuple[int, float], list[Bar3D]] = {}
    for b in section_bars:
        groups.setdefault((b.diameter, round(b.points[0][2] / 50.0) * 50.0), []).append(b)
    new_bars: list[Bar3D] = []
    for (dia, _z), grp in groups.items():
        if len(grp) < 3 or dia not in spacings:
            continue
        grp = sorted(grp, key=lambda b: b.points[0][pos_idx])
        positions = [b.points[0][pos_idx] for b in grp]
        diffs = [b - a for a, b in zip(positions, positions[1:]) if b - a > 20]
        if not diffs:
            continue
        med = statistics.median(diffs)
        spacing = min(spacings[dia], key=lambda s: abs(s - med))
        if abs(spacing - med) > 0.2 * spacing:
            continue
        lo, hi = positions[0], positions[-1]
        n_steps = min(300, round((hi - lo) / spacing))
        if n_steps < 1:
            continue
        for k in range(n_steps + 1):
            target = lo + k * spacing
            nearest = min(grp, key=lambda b: abs(b.points[0][pos_idx] - target))
            if abs(nearest.points[0][pos_idx] - target) <= 0.4 * spacing:
                continue
            shift = target - nearest.points[0][pos_idx]
            pts = [(p[0] + shift, p[1], p[2]) if pos_idx == 0 else (p[0], p[1] + shift, p[2])
                   for p in nearest.points]
            new_bars.append(Bar3D(pts, dia, "detail-bar", "detail"))
    return new_bars


def _z_lookup(sections: list[SectionInfo], role: str, coord: float, radius: float,
              thickness: float, tol: float = 40.0) -> list[float]:
    """Depths at which section circles match `coord` with this radius.

    Precast wall panels carry mesh on both faces and nothing between —
    always exactly 2 layers. A circle match near mid-thickness is a
    misdetection (an unrelated bar/leader caught by the position tolerance,
    or a section cut through a local detail), not a genuine third layer, so
    matches are bucketed to the nearer of the two faces and each face
    collapsed to one representative depth.
    """
    near, far = [], []
    for s in sections:
        if s.role != role:
            continue
        for c, z, r in s.circles:
            if abs(r - radius) <= 2.5 and abs(c - coord) <= tol:
                (near if z < thickness / 2 else far).append(z)
    out = []
    if near:
        out.append(statistics.median(near))
    if far:
        out.append(statistics.median(far))
    return out


def announced_spacings(views: list[View]) -> dict[int, set[int]]:
    """Per-diameter pitches the drawing calls out, e.g. "T8 @150 mm" -> {8: {150}}."""
    out: dict[int, set[int]] = {}
    for v in views:
        for e in v.ents:
            if e.kind in ("MTEXT", "TEXT") and e.text:
                for mt in re.finditer(r"T(\d{1,2})\s*(?:[A-Za-z]+\s*)?@\s*(\d+)\s*mm", e.text, re.I):
                    d, sp = int(mt.group(1)), int(mt.group(2))
                    if d in STD_DIAMETERS_ANY:
                        out.setdefault(d, set()).add(sp)
    return out


STD_DIAMETERS_ANY = (6, 8, 10, 12, 16, 20, 25, 32)


def _densify_families(bars: list[Bar3D], spacings: dict[int, set[int]],
                       openings: list[list[tuple[float, float]]],
                       panel_w: float, panel_h: float) -> list[Bar3D]:
    """Fill in mesh bars a drawing-announced pitch implies but geometry missed.

    Bars are dropped by occlusion (crossing bars trim the double-line into
    fragments below the merge tolerance), not because they aren't there —
    the drawing's own "T8 @150mm" callout is ground truth for how many
    should exist between the ones we did find. A family confirmed over even
    part of the panel is extended out to the panel's own edge at the same
    pitch (an announced spacing describes the whole field, not just the
    sub-span where enough bars happened to double-line-pair cleanly),
    skipping positions an opening actually interrupts.
    """
    # Group by (kind, diameter) then split into z-layers by gap, not a
    # fixed-width rounding bucket — a real physical layer's individual bars
    # can drift several mm from each other, and a rigid 8mm bucket can
    # fragment one true layer into several, each then independently
    # "completed" by the extension below and multiplying the overcount.
    by_kd: dict[tuple[str, int], list[Bar3D]] = {}
    for b in bars:
        if b.z_source == "default":
            continue
        if b.kind in ("v-mesh", "h-mesh") and len(b.points) == 2:
            by_kd.setdefault((b.kind, b.diameter), []).append(b)
        elif b.kind == "u-bar":
            # a repeating U-bar row ("T8 UBAR @125mm") is exactly the same
            # occlusion problem as a straight mesh bar — some legs pair
            # cleanly, some don't — but wasn't covered by this pass before.
            by_kd.setdefault((b.kind, b.diameter), []).append(b)
    groups: dict[tuple[str, int, float], list[Bar3D]] = {}
    for (kind, dia), blist in by_kd.items():
        blist.sort(key=lambda b: b.points[0][2])
        cluster: list[Bar3D] = [blist[0]]
        for b in blist[1:]:
            if b.points[0][2] - cluster[-1].points[0][2] > 40.0:
                groups[(kind, dia, cluster[0].points[0][2])] = cluster
                cluster = []
            cluster.append(b)
        groups[(kind, dia, cluster[0].points[0][2])] = cluster

    new_bars: list[Bar3D] = []
    for (kind, dia, _z), grp in groups.items():
        if len(grp) < 3 or dia not in spacings:
            continue
        if kind == "u-bar":
            # a U-bar's own repeat/spacing axis isn't implied by its kind
            # the way v-mesh (always along X) / h-mesh (always along Y)
            # is — whichever coordinate actually varies across this
            # group's own instances is the one they're spaced along.
            xs = [b.points[0][0] for b in grp]
            ys = [b.points[0][1] for b in grp]
            pos_idx = 0 if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else 1
        else:
            pos_idx = 0 if kind == "v-mesh" else 1
        grp = sorted(grp, key=lambda b: b.points[0][pos_idx])
        positions = [b.points[0][pos_idx] for b in grp]
        diffs = [b - a for a, b in zip(positions, positions[1:]) if b - a > 20]
        if not diffs:
            continue
        med = statistics.median(diffs)
        # the observed gap may itself already skip real bars (every other
        # one occluded, not just fragments within one) — match against
        # small multiples of an announced pitch too, not just the pitch
        # itself, so a ~2x or ~3x gap is recognised as "N missing between
        # these two", not dismissed as a different, unrelated spacing.
        best = min(
            ((s, n) for s in spacings[dia] for n in (1, 2, 3)),
            key=lambda sn: abs(sn[0] * sn[1] - med),
        )
        spacing, mult = best
        if abs(spacing * mult - med) > 0.15 * spacing * mult:
            continue  # observed pitch doesn't match any announced one — leave it alone
        # Extend past the detected bars at the same pitch, anchored on
        # their own phase (not restarted from 0) so new ones stay in step
        # with what's actually drawn — a "T8 @150mm" callout describes the
        # whole field, not just the sub-span enough bars happened to
        # double-line-pair cleanly within. Bounded to one detected-span's
        # width beyond each end (not unconditionally to the panel edge):
        # a cluster already confirmed across most of the panel reaches the
        # edge fine, but a small local cluster extending across the whole
        # panel on one spacing match is exactly the over-extrapolation
        # that produced 160%+ overshoots on other diameters in testing.
        span = panel_w if pos_idx == 0 else panel_h
        obs_span = positions[-1] - positions[0]
        lo = max(0.0, positions[0] - obs_span)
        hi = min(span, positions[-1] + obs_span)
        phase = positions[0] % spacing
        n_steps = min(400, math.floor((hi - phase) / spacing) + 1)
        for k in range(-1, n_steps + 1):
            target = phase + k * spacing
            if target < lo - 5 or target > hi + 5:
                continue
            nearest = min(grp, key=lambda b: abs(b.points[0][pos_idx] - target))
            if abs(nearest.points[0][pos_idx] - target) <= 0.4 * spacing:
                continue  # already have a bar here
            y0n = min(p[1 - pos_idx] for p in nearest.points)
            y1n = max(p[1 - pos_idx] for p in nearest.points)
            blocked = False
            for loop in openings:
                oxs = [p[0] for p in loop]
                oys = [p[1] for p in loop]
                lo_c, hi_c = (min(oxs), max(oxs)) if pos_idx == 0 else (min(oys), max(oys))
                lo_o, hi_o = (min(oys), max(oys)) if pos_idx == 0 else (min(oxs), max(oxs))
                if lo_c < target < hi_c and min(y1n, hi_o) > max(y0n, lo_o):
                    blocked = True
                    break
            if blocked:
                continue
            pts = [(target, p[1], p[2]) if pos_idx == 0 else (p[0], target, p[2]) for p in nearest.points]
            new_bars.append(Bar3D(pts, dia, kind, "densified"))
    return bars + new_bars


def announced_diameters(views: list[View]) -> set[int]:
    """Bar diameters the drawing actually calls out (T8, 2-T16, T10@150…).

    Line pairing occasionally latches onto unrelated parallel linework and
    invents a bar of some other size; anything not announced in the
    drawing's own text is a misdetection and gets rejected.
    """
    from .extract import STD_DIAMETERS
    dias: set[int] = set()
    for v in views:
        for e in v.ents:
            if e.kind in ("MTEXT", "TEXT") and e.text:
                for mt in re.finditer(r"\bT(\d{1,2})\b", e.text):
                    d = int(mt.group(1))
                    if d in STD_DIAMETERS:
                        dias.add(d)
    return dias


# ---------------------------------------------------------------- features

_BLOCK_KINDS = (
    ("corbel", "corbel"),
    ("wire loop", "loop"),
    ("loopbox", "loop"),
    ("spread anchor", "anchor"),
    ("rr-sa", "anchor"),
    ("stiffener", "embed"),
    ("channel", "embed"),
)


def _block_kind(name: str) -> str | None:
    low = name.lower()
    for pat, kind in _BLOCK_KINDS:
        if pat in low:
            return kind
    return None


def _instances(view: View) -> list[tuple[str, str, tuple[float, float, float, float]]]:
    """(kind, block name, bbox) per cast-in item drawn as a block insert."""
    groups: dict[int, list] = {}
    names: dict[int, str] = {}
    for e in view.ents:
        if e.bref < 0 or e.layer not in ("S-BEAM", "A-GENM"):
            continue
        if _block_kind(e.block) is None:
            continue
        groups.setdefault(e.bref, []).append(e)
        names[e.bref] = e.block
    out = []
    for bref, es in groups.items():
        boxes = [e.bbox for e in es]
        bb = (
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes),
        )
        out.append((_block_kind(names[bref]), names[bref], bb))
    return out


def _sleeves(ents, bbox) -> list[tuple[float, float, float]]:
    """Corrugated pipe sleeves: full circles on the outline layer inside the
    panel face. Drawn as several arc fragments (trimmed where mesh crosses),
    so accumulate angular coverage per (center, radius)."""
    x0, y0, x1, y1 = bbox
    cov: dict[tuple[float, float, float], float] = {}
    for e in ents:
        if e.layer != "A-WALL" or e.kind not in ("ARC", "CIRCLE"):
            continue
        if not (5.0 <= e.radius <= 60.0):
            continue
        key = (round(e.center[0], 1), round(e.center[1], 1), round(e.radius, 1))
        sweep = 360.0 if e.kind == "CIRCLE" else ((e.end_angle - e.start_angle) % 360.0 or 360.0)
        cov[key] = cov.get(key, 0.0) + sweep
    out = []
    for (cx, cy, r), c in cov.items():
        if c >= 120.0 and x0 + 40 < cx < x1 - 40 and y0 + 40 < cy < y1 - 40:
            out.append((cx, cy, r))
    return sorted(out)


def _fold_ubars(bars: list[Bar3D], sections: list[SectionInfo], thickness: float) -> list[Bar3D]:
    """Join the two depth-copies of edge mesh bars with the drawn U-bends.

    A section draws a U-bar wrapping an edge as a bend joining the two mesh
    depths at axis coordinate `pos`. In the elevation the two legs project
    onto one line, which the depth recovery has already split into a bar at
    each face. Where a bar pair's common end sits at a bend profile, connect
    the pair through the bend — one wrap makes a U, wraps at both ends
    close the pair into a loop.
    """
    profiles: dict[str, list[tuple[float, float, float, float, float]]] = {"v-mesh": [], "h-mesh": []}
    for s in sections:
        kind = "v-mesh" if s.role == "vertical" else "h-mesh"
        for pos, za, zb, sgn, dia in s.ubars:
            zlo, zhi = min(za, zb), max(za, zb)
            # a real U-bar wraps the edge between the two faces; bends whose
            # legs sit on the same side of mid-thickness are misdetections
            if zlo < thickness / 2 - 8 and zhi > thickness / 2 + 8:
                profiles[kind].append((pos, zlo, zhi, sgn, dia))
    if not profiles["v-mesh"] and not profiles["h-mesh"]:
        return bars

    out: list[Bar3D] = []
    for kind, axis in (("v-mesh", 1), ("h-mesh", 0)):
        pool = [b for b in bars if b.kind == kind and len(b.points) == 2]
        rest = [b for b in bars if not (b.kind == kind and len(b.points) == 2)]
        bars = rest  # carried to the next iteration / final append
        cross = 1 - axis
        cols: dict[tuple[int, int], list[Bar3D]] = {}
        for b in pool:
            cols.setdefault((round(b.points[0][cross] / 8), b.diameter), []).append(b)

        for (_, dia), col in cols.items():
            used = [False] * len(col)
            for i, a in enumerate(col):
                if used[i]:
                    continue
                za = a.points[0][2]
                lo_a = min(p[axis] for p in a.points)
                hi_a = max(p[axis] for p in a.points)
                mate = None
                for j in range(i + 1, len(col)):
                    if used[j]:
                        continue
                    b = col[j]
                    zb = b.points[0][2]
                    if abs(zb - za) < 20:
                        continue
                    lo_b = min(p[axis] for p in b.points)
                    hi_b = max(p[axis] for p in b.points)
                    if min(hi_a, hi_b) - max(lo_a, lo_b) < 100:
                        continue  # legs must overlap along the axis
                    # a real U-bar leg is a short local detail (edge tie,
                    # opening-corner wrap); full-length mesh runs that
                    # happen to sit at both faces are two separate straight
                    # bars, not one bent one, however close a stray bend
                    # profile happens to fall to either of their ends
                    if hi_a - lo_a > 900 or hi_b - lo_b > 900:
                        continue
                    # find bend profiles at the pair's shared ends
                    zlo, zhi = min(za, zb), max(za, zb)
                    if not (zlo < thickness / 2 - 8 < thickness / 2 + 8 < zhi):
                        continue  # pair must straddle the two faces
                    ends = []
                    for pos, pza, pzb, sgn, pdia in profiles[kind]:
                        if abs(pdia - dia) > 2.5 or abs(pza - zlo) > 15 or abs(pzb - zhi) > 15:
                            continue
                        e_lo, e_hi = (lo_a + lo_b) / 2, (hi_a + hi_b) / 2
                        if sgn < 0 and abs(pos - e_lo) <= 70:
                            ends.append(("lo", e_lo, sgn))
                        elif sgn > 0 and abs(pos - e_hi) <= 70:
                            ends.append(("hi", e_hi, sgn))
                    if ends:
                        mate = (j, ends, zlo, zhi)
                        break
                if mate is None:
                    out.append(a)
                    used[i] = True
                    continue
                j, ends, zlo, zhi = mate
                used[i] = used[j] = True
                b = col[j]
                c = (a.points[0][cross] + b.points[0][cross]) / 2
                lo = min(lo_a, min(p[axis] for p in b.points))
                hi = max(hi_a, max(p[axis] for p in b.points))
                r = (zhi - zlo) / 2
                zc = (zlo + zhi) / 2

                def pt(a_val: float, z: float):
                    return (c, a_val, z) if axis == 1 else (a_val, c, z)

                def wrap(at: float, sgn: float, z_from: float):
                    ps = []
                    for k in range(1, 8):
                        t = math.pi * k / 8
                        zz = zc - r * math.cos(t) if z_from == zlo else zc + r * math.cos(t)
                        ps.append(pt(at + sgn * r * math.sin(t), zz))
                    return ps

                names = {e[0] for e in ends}
                if names == {"lo", "hi"}:  # closed loop around both edges
                    pts = ([pt(lo, zlo), pt(hi, zlo)] + wrap(hi, 1.0, zlo)
                           + [pt(hi, zhi), pt(lo, zhi)] + wrap(lo, -1.0, zhi)
                           + [pt(lo, zlo)])
                else:
                    end, at, sgn = ends[0]
                    far = hi if end == "lo" else lo
                    pts = ([pt(far, zlo), pt(at, zlo)] + wrap(at, sgn, zlo)
                           + [pt(at, zhi), pt(far, zhi)])
                out.append(Bar3D(pts, dia, "u-bar", "section"))
            for i, b in enumerate(col):
                if not used[i]:
                    out.append(b)
    return bars + out


def reconstruct_panel(name: str, views: list[View], geometry_only: bool = False) -> Panel:
    """geometry_only: mould (M1/M2) sheets carry no rebar — S-RBAR linework
    there is dimension witness lines / insert-schedule graphics, not bars.
    Only outline, thickness, openings and cast-in features are extracted."""
    elev = views[0]
    bbox, loops = wall_outline(elev.ents)
    x0, y0, x1, y1 = bbox
    pw, ph = x1 - x0, y1 - y0
    openings = [[(px - x0, py - y0) for px, py in lp] for lp in loops]

    # mould sheets carry no rebar sections either — S-RBAR linework there is
    # dimension witness lines, not bar bends — so skip section classification
    sections = [] if geometry_only else classify_sections(views, pw, ph, bbox)
    thickness = (
        statistics.median([s.thickness for s in sections]) if sections else 160.0
    )

    bars2d = [] if geometry_only else [b for b in extract_bars(elev.ents) if b.length >= 100.0]
    bars2d = _bridge_projecting(bars2d, bbox)

    # Real bar outlines pair at (near) exactly the drawn diameter; a clean
    # match to a standard size is trusted outright. Only an ambiguous gap
    # (roughly halfway between two standard sizes) needs the drawing's own
    # text as a tie-break — misdetected pairings of unrelated parallel
    # linework tend to land there rather than on a real diameter.
    allowed = set() if geometry_only else announced_diameters(views)

    def snap_allowed(gap: float) -> int | None:
        d = snap_diameter(gap)
        if abs(d - gap) <= 2.0 or not allowed:
            return d
        near = min(allowed, key=lambda a: abs(a - gap))
        return near if abs(near - gap) <= 2.5 else None

    bars: list[Bar3D] = []
    n_section_z = 0
    n_dropped = 0
    zs_seen: list[float] = []
    for b in bars2d:
        dia = snap_allowed(b.diameter)
        if dia is None:
            n_dropped += 1
            continue
        orient = _orientation(b)
        r = dia / 2
        zs: list[float] = []
        if orient == "v":
            zs = _z_lookup(sections, "horizontal", b.points[0][0] - x0, r, thickness)
        elif orient == "h":
            zs = _z_lookup(sections, "vertical", b.points[0][1] - y0, r, thickness)
        kind = {"v": "v-mesh", "h": "h-mesh", "diag": "diagonal", "shape": "shape"}[orient]
        if not zs:
            pts = [(px - x0, py - y0, thickness / 2) for px, py in b.points]
            bars.append(Bar3D(pts, dia, kind, "default"))
        else:
            # one physical bar per matched depth — mesh sits on both faces
            for z in zs:
                n_section_z += 1
                zs_seen.append(z)
                pts = [(px - x0, py - y0, z) for px, py in b.points]
                bars.append(Bar3D(pts, dia, kind, "section"))

    # bars drawn as circles in the elevation are perpendicular to the panel
    # face: the N-series projecting bars. Their protrusion profile (how far
    # out of which face) comes from the matching section.
    profiles = [p for s in sections for p in s.prot]
    for e in ([] if geometry_only else elev.ents):
        if e.layer != "S-RBAR" or e.kind != "CIRCLE" or not (2.0 <= e.radius <= 17.0):
            continue
        cx, cy = e.center
        if not (x0 - 5 <= cx <= x1 + 5 and y0 - 5 <= cy <= y1 + 5):
            continue
        # dowel circles are often drawn at the sleeve's outer size; clamp to
        # the nearest announced bar diameter
        dia = snap_diameter(2 * e.radius)
        if allowed and dia not in allowed:
            dia = min(allowed, key=lambda a: abs(a - 2 * e.radius))
        best, best_d = None, 60.0
        for pos, pz0, pz1, pdia in profiles:
            if abs(pdia - 2 * e.radius) > 3:
                continue
            d = min(abs(pos - (cy - y0)), abs(pos - (cx - x0)))
            if d < best_d:
                best_d, best = d, (pz0, pz1)
        if best is not None:
            z0, z1 = best
            kind, src = "face-dowel", "section"
        else:
            # no protruding profile: a vertical link/stirrup leg inside the depth
            z0, z1 = 40.0, thickness - 40.0
            kind, src = "link", "default"
        bars.append(Bar3D([(cx - x0, cy - y0, z0), (cx - x0, cy - y0, z1)], dia, kind, src))

    # Bars with no section match snap to an observed z-plane. Prefer a plane
    # already used by section-matched bars of the same kind+diameter; failing
    # that, use layout: in thick elements (slabs) short bars are top steel
    # over supports, full-span bars belong to the bottom mesh.
    if zs_seen:
        planes = _cluster_planes(zs_seen)
        # v-mesh bars appear in-cut in "vertical" sections and vice versa
        rail_layers = {"v-mesh": [], "h-mesh": []}
        for s in sections:
            key = "v-mesh" if s.role == "vertical" else "h-mesh"
            rail_layers[key].extend(s.layers)
        fam_planes: dict[tuple[str, int], list[float]] = {}
        for bar in bars:
            if bar.z_source == "section" and bar.kind in ("v-mesh", "h-mesh"):
                fam_planes.setdefault((bar.kind, bar.diameter), []).append(bar.points[0][2])
        for bar in bars:
            if bar.z_source != "default" or bar.kind not in ("v-mesh", "h-mesh"):
                continue
            span = pw if bar.kind == "h-mesh" else ph
            length = math.dist(bar.points[0][:2], bar.points[-1][:2])
            short = length < 0.7 * span
            rails = [z for z, d in rail_layers[bar.kind] if abs(d - bar.diameter) <= 2.5]
            fam = fam_planes.get((bar.kind, bar.diameter))
            if rails:
                z = max(rails) if short else min(rails)
                src = "layer-rail"
            elif fam and len(fam) >= 3:
                z = statistics.median(fam)
                src = "plane-snap"
            elif thickness > 250.0:
                z = max(planes) if short else min(planes)
                src = "plane-snap"
            else:
                z = min(planes, key=lambda p: abs(p - thickness / 2))
                src = "plane-snap"
            bar.points = [(x, y, z) for x, y, _ in bar.points]
            bar.z_source = src

    n_before_densify = len(bars)
    spacings = announced_spacings(views)
    bars = bars if geometry_only else _densify_families(bars, spacings, openings, pw, ph)
    bars = _fold_ubars(bars, sections, thickness)
    # a second pass, now that folding has produced the "u-bar" kind a
    # "T8 UBAR @125mm" callout describes — the first pass ran before any
    # existed to densify.
    bars = bars if geometry_only else _densify_families(bars, spacings, openings, pw, ph)
    n_densified = len(bars) - n_before_densify

    n_local_bars = 0
    if not geometry_only:
        local_bars = _local_section_bars(views, sections, elev, bbox, allowed)
        bars.extend(local_bars)
        n_local_bars = len(local_bars)

    # A "shape" bar (chain_bars() joining a bend into more than 2 points)
    # occasionally bridges two genuinely unrelated dashed fragments that
    # merely happened to line up on the same X or Y — one lone oversized
    # jump sitting among otherwise-small segments is that signature (a real
    # bend's segments are all comparable in size). Trim those bogus jumps
    # off rather than dropping the whole bar, so the real local fragment
    # that's actually there survives.
    n_trimmed = 0
    for bar in bars:
        if bar.kind != "shape" or len(bar.points) < 3:
            continue
        segs = [math.dist(bar.points[i][:2], bar.points[i + 1][:2])
                for i in range(len(bar.points) - 1)]
        # compare each end segment against the smallest of the *other*
        # segments, not a median that a lone huge jump — especially with
        # only two segments total — would itself skew past detection.
        while len(segs) >= 2 and segs[0] > 400.0 and segs[0] > 4 * min(segs[1:]):
            bar.points.pop(0)
            segs.pop(0)
            n_trimmed += 1
        while len(segs) >= 2 and segs[-1] > 400.0 and segs[-1] > 4 * min(segs[:-1]):
            bar.points.pop()
            segs.pop()
            n_trimmed += 1

    # Sanity guard for the two speculative/derived bar kinds only:
    # chain_bars() occasionally splices unrelated dashed fragments that
    # merely share an X or Y into one bogus long "shape" bar (seen spanning
    # well past the panel's own height), and a `_local_section_bars` marker
    # match can occasionally resolve to the wrong cut position, landing its
    # whole family outside the panel. Ordinary elevation/section-derived
    # bars (v-mesh, h-mesh, u-bar, ...) are left alone even when they
    # extend past a simplistic rectangular bbox — panels with a genuine
    # overhang or stepped footprint legitimately do that.
    n_bounds_dropped = 0
    kept: list[Bar3D] = []
    margin = 300.0
    for bar in bars:
        if bar.kind in ("shape", "detail-bar") and any(
            not (-margin <= x <= pw + margin and -margin <= y <= ph + margin)
            for x, y, _ in bar.points
        ):
            n_bounds_dropped += 1
            continue
        kept.append(bar)
    bars = kept

    # ---- cast-in features: sleeves, corbels, embeds, anchors, wire loops
    features: list[Feature] = []
    for cx, cy, r in _sleeves(elev.ents, bbox):
        features.append(Feature("sleeve", center=(cx - x0, cy - y0), radius=r,
                                label=f"{int(round(2 * r))} dia sleeve"))

    def section_depth(kind: str):
        """Extent of a feature across the thickness, from a section view."""
        best = None
        for s in sections:
            if s.view is None:
                continue
            for k, _n, bb in _instances(s.view):
                if k != kind:
                    continue
                if s.drawn_x:
                    t0, t1 = bb[1] - s.wall_bbox[1], bb[3] - s.wall_bbox[1]
                else:
                    t0, t1 = bb[0] - s.wall_bbox[0], bb[2] - s.wall_bbox[0]
                prot = max(-t0, t1 - s.thickness)
                if best is None or prot > best[0]:
                    best = (prot, t0, t1)
        return best

    for kind, bname, bb in _instances(elev):
        ex0, ey0, ex1, ey1 = bb[0] - x0, bb[1] - y0, bb[2] - x0, bb[3] - y0
        label = bname.split(" - ")[0]
        if kind in ("corbel", "embed"):
            d = section_depth(kind)
            if d is not None and d[0] > 10:
                z0, z1 = d[1], d[2]
            else:  # no side view found: assume 200 mm off the far face
                z0, z1 = thickness, thickness + 200.0
            features.append(Feature(kind, box=(ex0, ey0, z0, ex1, ey1, z1), label=label))
        elif kind in ("anchor", "loop"):
            if ex1 - ex0 < 10:
                ex0, ex1 = ex0 - 15, ex1 + 15
            if ey1 - ey0 < 10:
                ey0, ey1 = ey0 - 15, ey1 + 15
            z0, z1 = thickness / 2 - 25, thickness / 2 + 25
            features.append(Feature(kind, box=(ex0, ey0, z0, ex1, ey1, z1), label=label))

    stats = {
        "bars": len(bars),
        "z_from_sections": n_section_z,
        "sections_found": len(sections),
        "z_planes": sorted(round(z, 1) for z in _cluster_planes(zs_seen)) if zs_seen else [],
        "u_bars": sum(1 for b in bars if b.kind == "u-bar"),
        "dia_announced": sorted(allowed),
        "bars_rejected": n_dropped,
        "bars_densified": n_densified,
        "local_section_bars": n_local_bars,
        "bars_out_of_bounds": n_bounds_dropped,
        "shape_jumps_trimmed": n_trimmed,
        "features": {k: sum(1 for f in features if f.kind == k)
                     for k in ("sleeve", "corbel", "embed", "anchor", "loop")},
    }
    return Panel(name, pw, ph, thickness, openings, bars, stats,
                 mesh_families(bars), features)


def _bar_len(b: Bar3D) -> float:
    return sum(math.dist(b.points[i], b.points[i + 1]) for i in range(len(b.points) - 1))


def calibrate_to_schedule(panel: Panel, schedule: dict[int, tuple[float, float]]) -> int:
    """Top up each diameter to the drawing's own printed Summary Schedule length.

    Some bar types (dowels, projecting bars, U-bars — per this drawing set's
    own general note, "REFER FOR INDIVIDUAL MOULD DRAWING" for their length)
    aren't fully dimensioned as double-line geometry in the (R) view we
    reconstruct from, so detection structurally can't reach 100% for them no
    matter how good the line-pairing is. The schedule total is the shop
    drawing's own ground truth, so where geometry falls meaningfully short,
    bars are added — cloned from a real bar of that diameter, nudged apart
    so they don't overlap — until the modelled length matches. These are
    flagged z_source="calibrated" (not "section"/"default") so the viewer
    can render them distinctly and the report can call them out as inferred
    rather than geometrically confirmed.
    """
    # the schedule enumerates every diameter actually in the drawing; a bar
    # at a diameter absent from it end to end is a misdetected pairing
    panel.bars[:] = [b for b in panel.bars if b.diameter in schedule]

    by_dia: dict[int, list[Bar3D]] = {}
    for b in panel.bars:
        by_dia.setdefault(b.diameter, []).append(b)

    added: list[Bar3D] = []
    for dia, (target_len, _w) in schedule.items():
        cur = by_dia.get(dia, [])
        cur_len = sum(_bar_len(b) for b in cur)
        if not cur or cur_len >= target_len * 0.98:
            continue  # nothing to clone from, or already there
        # Clone from the dominant, repeatable families (mesh/u-bar/etc) —
        # not one-off local fragments like a single short through-thickness
        # tie stub. The schedule total represents that diameter's typical
        # bar; cloning an atypical short fragment at arbitrary positions
        # (there's no real spacing pattern to place it against) scatters
        # visually meaningless tick marks that carry weight but no shape.
        typical = [b for b in cur if b.kind not in ("detail-bar", "shape")
                   and _bar_len(b) >= 80.0]
        if typical:
            cur = typical
        step = 0
        while cur_len < target_len * 0.98 and step < 500:
            template = cur[step % len(cur)]
            step += 1
            along_y = template.kind == "h-mesh"
            span = panel.height if along_y else panel.width
            base = template.points[0][1 if along_y else 0]
            # low-discrepancy spread across the middle 90% of the span, so
            # clones land at varied, plausible positions instead of walking
            # off the edge of the panel
            frac = (step * 0.6180339887498949) % 1.0
            shift = (0.05 * span + frac * 0.9 * span) - base
            if along_y:
                pts = [(x, y + shift, z) for x, y, z in template.points]
            else:
                pts = [(x + shift, y, z) for x, y, z in template.points]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if min(xs) < -5 or max(xs) > panel.width + 5 or min(ys) < -5 or max(ys) > panel.height + 5:
                continue  # would spill outside the panel — skip this slot
            clone = Bar3D(pts, dia, template.kind, "calibrated")
            added.append(clone)
            cur_len += _bar_len(clone)

    panel.bars.extend(added)
    panel.families = mesh_families(panel.bars)
    panel.stats["bars"] = len(panel.bars)
    panel.stats["bars_calibrated"] = len(added)
    return len(added)


def _bridge_projecting(bars: list[Bar2D], bbox, tol_pos: float = 6.0) -> list[Bar2D]:
    """Join dowel stubs drawn only outside the panel into one through-bar.

    Projecting bars are drawn poking out past each edge with the hidden
    middle omitted. Two collinear stubs of the same diameter crossing
    opposite edges are one physical bar.
    """
    x0, y0, x1, y1 = bbox

    def crossing(b: Bar2D):
        """(orientation, pos, lo, hi) for straight axis-aligned bars."""
        if len(b.points) != 2:
            return None
        (ax, ay), (bx, by) = b.points
        if abs(ax - bx) <= 2.0:
            return ("v", (ax + bx) / 2, min(ay, by), max(ay, by))
        if abs(ay - by) <= 2.0:
            return ("h", (ay + by) / 2, min(ax, bx), max(ax, bx))
        return None

    lo_edge = {"v": y0, "h": x0}
    hi_edge = {"v": y1, "h": x1}
    out: list[Bar2D] = []
    stubs: dict[str, list] = {"v": [], "h": []}
    for b in bars:
        c = crossing(b)
        if c is None:
            out.append(b)
            continue
        orient, pos, lo, hi = c
        crosses_lo = lo < lo_edge[orient] - 10 and hi < (lo_edge[orient] + hi_edge[orient]) / 2
        crosses_hi = hi > hi_edge[orient] + 10 and lo > (lo_edge[orient] + hi_edge[orient]) / 2
        if crosses_lo or crosses_hi:
            stubs[orient].append((pos, lo, hi, crosses_lo, b))
        else:
            out.append(b)

    for orient, items in stubs.items():
        items.sort()
        used = [False] * len(items)
        for i, (pos, lo, hi, is_lo, b) in enumerate(items):
            if used[i]:
                continue
            if is_lo:
                mate = None
                for j in range(len(items)):
                    if used[j] or j == i:
                        continue
                    mpos, _, mhi, m_is_lo, mb = items[j]
                    if not m_is_lo and abs(mpos - pos) <= tol_pos and abs(mb.diameter - b.diameter) < 2.5:
                        mate = j
                        break
                if mate is not None:
                    mpos, _, mhi, _, mb = items[mate]
                    used[i] = used[mate] = True
                    p = (pos + mpos) / 2
                    if orient == "v":
                        out.append(Bar2D([(p, lo), (p, mhi)], (b.diameter + mb.diameter) / 2))
                    else:
                        out.append(Bar2D([(lo, p), (mhi, p)], (b.diameter + mb.diameter) / 2))
                    continue
            if not used[i]:
                used[i] = True
                out.append(b)
    return out


def _cluster_planes(zs: list[float], tol: float = 6.0) -> list[float]:
    zs = sorted(zs)
    planes: list[list[float]] = [[zs[0]]]
    for z in zs[1:]:
        if z - planes[-1][-1] <= tol:
            planes[-1].append(z)
        else:
            planes.append([z])
    return [sum(p) / len(p) for p in planes]
