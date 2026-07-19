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

from .extract import Bar2D, _Seg, extract_bars, snap_diameter, wall_outline
from .views import View

AXIS_TOL = math.radians(3)


@dataclass
class Bar3D:
    points: list[tuple[float, float, float]]
    diameter: int
    kind: str  # v-mesh | h-mesh | diagonal | shape | u-bar | face-dowel | link
    z_source: str  # section | default
    pos: float = 0.0  # fixed cross-axis coordinate, set for "section-origin" bars only


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
    # First pass: every view's own A-WALL/A-FLOR bbox gives a candidate
    # thickness (its short axis) before any of the expensive per-view work
    # below. A view whose "wall" bbox actually captures unrelated geometry
    # alongside the true cut (confirmed on PW-01: a bbox reading 275mm when
    # the panel is genuinely 125mm thick, from a foundation/dowel detail
    # sharing the same layer prefix) produces a wildly wrong z downstream --
    # any bar z_lookup pulls from it lands outside [0, thickness] entirely
    # (observed z=217mm in a 125mm-thick panel). The lone 0.5x-panel-size
    # gate below is too loose to catch this (275mm easily passes it). Use
    # the *median* candidate thickness across every view as a robust
    # consensus of the real value, and reject any view whose own candidate
    # deviates from it by more than 30% (a genuine section-to-section
    # thickness variance in one drawing is not expected to be that large;
    # only compute the consensus from views close enough to plausibly be
    # real -- if all candidates already agree there's nothing to filter).
    candidates = []
    for v in views[1:]:
        wall = [e for e in v.ents if e.layer.startswith("A-WALL")]
        if not wall:
            wall = [e for e in v.ents if e.layer.startswith("A-FLOR")]
        if not wall:
            continue
        xs = [b for e in wall for b in (e.bbox[0], e.bbox[2])]
        ys = [b for e in wall for b in (e.bbox[1], e.bbox[3])]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        t = min(w, h)
        if t <= 0.5 * min(panel_w, panel_h):
            candidates.append(t)
    consensus_t = statistics.median(candidates) if candidates else None

    infos: list[SectionInfo] = []
    for v in views[1:]:
        wall = [e for e in v.ents if e.layer.startswith("A-WALL")]
        if not wall:
            wall = [e for e in v.ents if e.layer.startswith("A-FLOR")]
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
        if consensus_t is not None and abs(thickness - consensus_t) > 0.3 * consensus_t:
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


def _z_lookup(sections: list[SectionInfo], role: str, coord: float, radius: float, tol: float = 40.0) -> list[float]:
    """All depths at which section circles match `coord` with this radius.

    The same bar position usually shows a circle near each face (mesh on
    both sides), and occasionally a genuine third/fourth layer (confirmed:
    one T8 position independently shows 3 real depths from 2 sections
    each) — returning every matched depth lets the caller emit one bar per
    layer instead of collapsing them into fewer bars than actually exist.

    The radius match used to allow +-2.5mm, wide enough to also match a
    *different* diameter's circles as if they were this one — adjacent
    standard bar radii are as little as 1mm apart (T8=4, T10=5, T12=6).
    Confirmed directly: a T12 bar was matching 5 depths where 3 independent
    section cuts agreed exactly on just 2 (46.9mm and 113.1mm) once
    filtered to its own radius; the other 2 were real depths belonging to
    a different diameter's own bar at the same position. That's pure
    contamination, unlike genuine multi-layer bars (still radius-clean at
    any tolerance) — so this fix removes real cross-diameter bleed without
    capping how many depths a single diameter can legitimately have.
    Section circles are drawn at essentially exact radii in this DXF
    (floating-point noise only), so a tight tolerance costs nothing.
    """
    zs = []
    for s in sections:
        if s.role != role:
            continue
        for c, z, r in s.circles:
            if abs(r - radius) <= 0.5 and abs(c - coord) <= tol:
                zs.append(z)
    return _cluster_planes(zs, tol=8.0) if zs else []


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


def _fold_ubars(bars: list[Bar3D], sections: list[SectionInfo]) -> list[Bar3D]:
    """Join the two depth-copies of edge mesh bars with the drawn U-bends.

    A section draws a U-bar wrapping an edge as a bend joining the two mesh
    depths at axis coordinate `pos`. In the elevation the two legs project
    onto one line, which the depth recovery has already split into a bar at
    each face. Where a bar pair's common end sits at a bend profile, connect
    the pair through the bend — one wrap makes a U, wraps at both ends
    close the pair into a loop.

    A profile legitimately applies to many rows when a drawing genuinely
    calls out "a U-bar at every bar" (e.g. "T8 UBAR @125mm") — confirmed
    directly: what first looked like a fabrication bug (20 closed loops
    stacked the full height of PW-GF-02 at one edge, rendering as a
    coil/spiral in the 3D viewer) turned out, on inspecting the actual
    data, to be 20 *different* real mesh rows at 20 different Y positions
    all legitimately wrapping the same physical edge — exactly what the
    pitch callout describes. A prior version of this function capped how
    many times one profile could be reused to "fix" that, which instead
    deleted ~85 other equally legitimate wraps across the panel (u_bars
    stat dropped from 88 to 5). Reverted — a profile is matched against
    every row whose end position agrees with it, with no reuse limit.
    """
    profiles: dict[str, list[tuple[float, float, float, float, int]]] = {"v-mesh": [], "h-mesh": []}
    for s in sections:
        kind = "v-mesh" if s.role == "vertical" else "h-mesh"
        for pos, za, zb, sgn, dia in s.ubars:
            sdia = snap_diameter(dia)
            if sdia is not None:
                profiles[kind].append((pos, min(za, zb), max(za, zb), sgn, sdia))
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
                    # find bend profiles at the pair's shared ends
                    zlo, zhi = min(za, zb), max(za, zb)
                    ends = []
                    for pos, pza, pzb, sgn, pdia in profiles[kind]:
                        if pdia != dia or abs(pza - zlo) > 15 or abs(pzb - zhi) > 15:
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


_TIE_RE = re.compile(r"T(\d+)\s*Ties?\s*@\s*(\d+)\s*mm", re.IGNORECASE)


def _synthesize_ties(bars: list[Bar3D], all_ents, thickness: float,
                     panel_h: float) -> list[Bar3D]:
    """Boundary-column stirrup ties, drawn too fragmented to pair as bars.

    Ties are drawn as hundreds of tiny fragments (many under pair_lines'
    6mm segment floor), so they never survive as paired bars; synthesize
    them from structural facts instead. The decoded BBS (BBS_RULES.md)
    pins the design down: the standard tie is a ~200mm-wide core loop
    wrapping a *pair* of adjacent main bars, at the callout's pitch —
    PW-GF-09's BBS count (174 = 6 runs x 29) matches 3 main-bar pairs per
    boundary column x 2 columns, at 100c/c over the clear height.

    Placement lessons from two earlier broken attempts, both now encoded:
    - main bars are the *larger*-diameter verticals (a tie's own diameter
      is the panel's smallest/most common — clustering those grabs the
      general field mesh, not a column);
    - main bars are routinely SPLIT vertically by side notches/openings
      (e.g. x=47 exists only at y 30-749 and 2225-2892) — a tie run must
      follow the intersection of its pair's actual y-intervals, clamped
      to the panel, never the naive min/max envelope (which drew ties
      across the notch and outside the panel outline entirely).
    """
    # count callout instances across ALL views: labels for tied pairs are
    # placed in whichever view shows the detail (on PW-GF-09 only 1 of the
    # 6 sits in the elevation; the BBS count needs all 6)
    callouts = []
    for e in all_ents:
        if e.kind not in ("TEXT", "MTEXT"):
            continue
        m = _TIE_RE.search(e.text or "")
        if m:
            callouts.append((int(m.group(1)), int(m.group(2))))
    if not callouts:
        return bars
    tie_dia, pitch = max(set(callouts), key=callouts.count)
    cover = 30.0

    # main bars: the column longitudinals, >=T12 (T10-and-under at a tight
    # pitch is field mesh -- PW-GF-09's "T10 @150mm" mesh sits 149mm apart,
    # inside the 160mm pairing threshold, and got wrongly tie-wrapped when
    # this only excluded the tie's own diameter). Grouped by x with each
    # bar's real y-intervals (split bars appear as several entries).
    main: dict[float, list[tuple[float, float]]] = {}
    for b in bars:
        if b.kind != "v-mesh" or b.diameter < 12 or b.diameter <= tie_dia:
            continue
        x = round(b.points[0][0], 0)
        ys = [p[1] for p in b.points]
        main.setdefault(x, []).append((min(ys), max(ys)))
    if not main:
        return bars

    def merged(iv: list[tuple[float, float]]) -> list[tuple[float, float]]:
        iv = sorted(iv)
        out = [list(iv[0])]
        for a, b2 in iv[1:]:
            if a <= out[-1][1] + 1:
                out[-1][1] = max(out[-1][1], b2)
            else:
                out.append([a, b2])
        return [(a, b2) for a, b2 in out]

    def intersect(a: list[tuple[float, float]], b: list[tuple[float, float]]):
        res = []
        for a0, a1 in a:
            for b0, b1 in b:
                lo, hi = max(a0, b0), min(a1, b1)
                if hi - lo > 2 * pitch:  # a run needs room for >=2 ties
                    res.append((lo, hi))
        return res

    # candidate tie stacks = adjacent main-bar pairs within ~160mm (tie
    # core is ~200mm wide). The number of stacks is the number of "Ties"
    # callout INSTANCES in the drawing -- the BBS tie count is exactly
    # instances x (H/pitch + 1) (BBS_RULES.md; 174 = 6 x 29 on PW-GF-09).
    # Rank candidate pairs by how much tie-able run they actually carry
    # and claim the best ones exclusively (a bar x can belong to one
    # stack only). The previous greedy left-to-right pairing of ALL
    # >=T12 columns fabricated overlapping partial stacks wherever
    # fragmented verticals clustered (observed: six phantom half-height
    # stacks on PW-GF-09's right side).
    n_stacks = callouts.count((tie_dia, pitch))
    xs = sorted(main)
    pairs = [(xs[i], xs[i + 1]) for i in range(len(xs) - 1)
             if xs[i + 1] - xs[i] <= 160.0]
    scored = []
    for a, b in pairs:
        runs = intersect(merged(main[a]), merged(main[b]))
        cov = sum(hi - lo for lo, hi in runs)
        if cov > 0:
            scored.append((cov, a, b, runs))
    scored.sort(key=lambda s: -s[0])
    claimed: set[float] = set()
    out: list[Bar3D] = []
    taken = 0
    for cov, a, b, runs in scored:
        if taken >= n_stacks:
            break
        if a in claimed or b in claimed:
            continue
        claimed.update((a, b))
        taken += 1
        x_lo, x_hi = a - cover, b + cover
        z_lo, z_hi = cover, thickness - cover
        for lo, hi in runs:
            lo = max(lo, cover)
            hi = min(hi, panel_h - cover)
            n = max(int((hi - lo) // pitch) + 1, 1)
            for k in range(n):
                y = lo + k * pitch
                # closed loop + two 80mm hook tails angled into the
                # core at the closing corner -- the BBS tie shape's
                # 0.08 end segments (0.632m total at T8/t160, vs 0.60
                # for the bare rectangle; see BBS_RULES.md)
                h = 80.0 / math.sqrt(2)
                t1 = (x_lo + h, y, z_lo + h)
                t2 = (x_lo + h, y, z_hi - h)
                pts = [t1, (x_lo, y, z_lo), (x_hi, y, z_lo), (x_hi, y, z_hi),
                       (x_lo, y, z_hi), t2]
                out.append(Bar3D(pts, tie_dia, "tie", "synthesized"))
    return bars + out


_UBAR_PITCH_RE = re.compile(r"T(\d+)\s*UBAR\s*@\s*(\d+)\s*mm", re.IGNORECASE)
_HOOK_RE = re.compile(r"T(\d+)\s*Hook\s*@\s*(\d+)\s*mm", re.IGNORECASE)


def _synthesize_hairpins(bars: list[Bar3D], elev_ents, thickness: float,
                         panel_h: float) -> list[Bar3D]:
    """Edge hairpins (the BBS's 0.4/web/0.4 'UBAR' row) at mesh bar ends.

    A hairpin links the two mesh faces where bars terminate at a free
    edge (panel edge or notch boundary). The BBS pins the shape exactly:
    400mm legs + a web of thickness-2*cover (0.868m at T8/t160), at the
    "T8 UBAR @pitch" callout's pitch — PW-GF-09's BBS row 10 wants 120 of
    them, far more than the ~40 loops the u-bar geometry folding detects.

    Placement is strictly evidence-anchored (fabricated placement burned
    this project twice): one hairpin per (x, end) of each *double-faced*
    v-mesh vertical of the callout's diameter — both faces ending at the
    same y is exactly the situation a hairpin exists to close — skipped
    when a geometry-detected u-bar already sits within 120mm. A column's
    two faces are intersected per contiguous run (not just the column's
    overall min/max y) so a column split by a side notch — the same
    real pattern `_synthesize_ties` already accounts for — gets a
    hairpin at each of its own free ends, not only the panel's outer
    top/bottom.
    """
    callouts = [(int(m.group(1)), int(m.group(2)))
                for e in elev_ents if e.kind in ("TEXT", "MTEXT")
                for m in [_UBAR_PITCH_RE.search(e.text or "")] if m]
    if not callouts:
        return bars
    dia, _pitch = max(set(callouts), key=callouts.count)
    cover = 30.0

    # double-faced verticals: same x, a z-plane pair, matching y-intervals
    by_x: dict[float, list[Bar3D]] = {}
    for b in bars:
        if b.kind == "v-mesh" and b.diameter == dia:
            by_x.setdefault(round(b.points[0][0], 0), []).append(b)

    existing = []  # (x, y) midpoints of detected u-bar bends
    for b in bars:
        if b.kind == "u-bar":
            existing.append((b.points[0][0], b.points[0][1]))

    def merge_ivs(ivs: list[tuple[float, float]]) -> list[tuple[float, float]]:
        ivs = sorted(ivs)
        out = [list(ivs[0])]
        for a, b2 in ivs[1:]:
            if a <= out[-1][1] + 5.0:
                out[-1][1] = max(out[-1][1], b2)
            else:
                out.append([a, b2])
        return [(a, b2) for a, b2 in out]

    web_lo, web_hi = cover, thickness - cover
    out: list[Bar3D] = []
    for x, group in by_x.items():
        by_z: dict[float, list[tuple[float, float]]] = {}
        for b in group:
            z = round(b.points[0][2], 0)
            ys = [p[1] for p in b.points]
            by_z.setdefault(z, []).append((min(ys), max(ys)))
        if len(by_z) < 2:
            continue  # hairpins close a two-face pair; single-face has none
        zs_sorted = sorted(by_z)
        common = merge_ivs(by_z[zs_sorted[0]])
        for z in zs_sorted[1:]:
            other = merge_ivs(by_z[z])
            common = [(max(a0, b0), min(a1, b1))
                      for a0, a1 in common for b0, b1 in other
                      if min(a1, b1) > max(a0, b0)]
        for lo, hi in common:
            for y_end, leg_dir in ((lo, 1.0), (hi, -1.0)):
                if any(abs(ex - x) < 120 and abs(ey - y_end) < 200 for ex, ey in existing):
                    continue
                if not (0 <= y_end <= panel_h):
                    continue  # a projecting stub's end isn't a panel free edge
                y_end_c = min(max(y_end, cover), panel_h - cover)
                leg = 400.0 * leg_dir
                if not (0 <= y_end_c + leg <= panel_h):
                    continue
                pts = [(x, y_end_c + leg, web_lo), (x, y_end_c, web_lo),
                       (x, y_end_c, web_hi), (x, y_end_c + leg, web_hi)]
                out.append(Bar3D(pts, dia, "u-bar", "synthesized"))
    return bars + out


def _hook_unit_length(views: list[View], dia: int) -> float | None:
    """Real drawn length of one "Hook" family unit (bend + legs), measured
    from whichever view actually draws it to true scale.

    The elevation only marks each instance with a small fixed-size icon --
    a handful of sub-16mm lines/arcs regardless of the real bar, confirmed
    directly on PW-GF-09's icon geometry (an 8x14mm cluster next to a
    100mm-pitch column of them). The real bend geometry lives in a
    same-named detail/section view elsewhere in the file as genuine
    concentric arc pairs at gap == dia; `radii[i] > 10.0` excludes the
    elevation's own icon arcs (radius == dia/2, well under 10mm) so only
    to-scale geometry is measured. Chained fragments in a detail view
    routinely span several repeat units end to end (confirmed: a single
    chain covering 6 hook bends + their connecting rail) -- dividing the
    view's total matching-diameter shape length by its own arc-pair count
    gives the per-unit average without needing to split the chain up.
    """
    unit_lens = []
    for v in views:
        arcs = [e for e in v.ents if e.kind == "ARC" and e.layer == "S-RBAR"]
        by_center: dict[tuple[float, float], set[float]] = {}
        for e in arcs:
            by_center.setdefault((round(e.center[0], 1), round(e.center[1], 1)),
                                  set()).add(round(e.radius, 1))
        n_units = 0
        for radii in by_center.values():
            radii = sorted(radii)
            for i in range(len(radii)):
                for j in range(i + 1, len(radii)):
                    if abs((radii[j] - radii[i]) - dia) < 1.5 and radii[i] > 10.0:
                        n_units += 1
        if n_units < 2:
            continue
        bars2d = extract_bars(v.ents, min_len=3.0)
        tot_len = sum(b.length for b in bars2d
                      if b.diameter and abs(b.diameter - dia) < 1.9 and len(b.points) > 2)
        if tot_len > 0:
            unit_lens.append(tot_len / n_units)
    return statistics.median(unit_lens) if unit_lens else None


def _icon_runs(elev_ents, dia: int, pitch: float) -> list[dict]:
    """Vertical/horizontal runs of the elevation's small fixed-size family
    marker (a single ARC/CIRCLE of radius == dia/2, stamped at every real
    instance's true panel position -- unlike the icon's own sub-8mm
    construction lines, position needs only the marker circle itself).

    A real family run is periodic at the callout's own pitch and long
    enough (>=5 members) to rule out coincidental same-radius circles
    elsewhere on the sheet (arrowheads, weld symbols, dimension origins --
    confirmed on PW-GF-09: 13 stray same-radius pairs with a >1000mm gap
    and only 2 members each, cleanly below this floor).
    """
    r_target = dia / 2.0
    centers: set[tuple[float, float]] = set()
    for e in elev_ents:
        if e.layer != "S-RBAR" or e.kind not in ("ARC", "CIRCLE"):
            continue
        if abs(e.radius - r_target) < 1.0:
            centers.add((round(e.center[0], 1), round(e.center[1], 1)))

    def cluster_1d(vals: list[float], tol: float) -> list[list[float]]:
        vals = sorted(vals)
        out = [[vals[0]]]
        for v in vals[1:]:
            if v - out[-1][-1] <= tol:
                out[-1].append(v)
            else:
                out.append([v])
        return out

    runs: list[dict] = []
    for axis, group_key, spread_key in (("v", 0, 1), ("h", 1, 0)):
        by_fixed: dict[float, list[float]] = {}
        for c in centers:
            by_fixed.setdefault(c[group_key], []).append(c[spread_key])
        for fixed, spread in by_fixed.items():
            for grp in cluster_1d(spread, pitch * 1.4):
                if len(grp) < 5:
                    continue
                gaps = [b - a for a, b in zip(grp, grp[1:])]
                med_gap = statistics.median(gaps)
                if med_gap and abs(med_gap - pitch) < 0.3 * pitch:
                    runs.append({"axis": axis, "coord": fixed,
                                 "lo": grp[0], "hi": grp[-1], "n": len(grp)})

    # collapse near-duplicate runs (jittered repeats of the same physical
    # feature at nearly the same location -- confirmed on PW-GF-09: 5
    # x-values within ~500mm of each other, each independently spanning
    # the exact same y-range): keep the one with the most members.
    runs.sort(key=lambda r: -r["n"])
    kept: list[dict] = []
    for r in runs:
        if any(k["axis"] == r["axis"] and abs(k["lo"] - r["lo"]) < 60
               and abs(k["hi"] - r["hi"]) < 60 and abs(k["coord"] - r["coord"]) < 700
               for k in kept):
            continue
        kept.append(r)
    return kept


def _synthesize_hooks(bars: list[Bar3D], views: list[View], thickness: float,
                      x0: float, y0: float) -> list[Bar3D]:
    """Boundary/edge "Hook" family bars, marked in the elevation only as a
    small fixed-size icon (never drawn to scale there) with their real
    bent geometry living in a separate, spatially-unrelated detail view.

    Correspondence rule (verified on PW-GF-09 before writing this):
    position/count/extent come from the elevation's own icon marks --
    those share the panel's real coordinate frame, so they need no
    cross-view mapping. Shape/length can't come from the elevation (the
    icon there is a fixed ~8-16mm glyph regardless of the real bar) --
    only from a same-named detail view's true concentric arc-pair
    geometry, measured as a per-unit average length and applied uniformly,
    since detail-view *coordinates* have no relation to panel space (huge,
    arbitrary offsets confirmed -- no shared origin or INSERT-block tie)
    even though the *shape itself* is drawn to true scale there.
    """
    callouts = [(int(m.group(1)), int(m.group(2)))
                for v in views for e in v.ents if e.kind in ("TEXT", "MTEXT")
                for m in [_HOOK_RE.search(e.text or "")] if m]
    if not callouts:
        return bars
    dia, pitch = max(set(callouts), key=callouts.count)

    unit_len = _hook_unit_length(views, dia)
    if unit_len is None or unit_len <= 0:
        return bars  # no view draws this family to scale -- no safe length to use

    cover = 30.0
    web_lo, web_hi = cover, thickness - cover
    zc = (web_lo + web_hi) / 2.0
    half = unit_len / 2.0

    runs = _icon_runs(views[0].ents, dia, pitch)
    out: list[Bar3D] = []
    for r in runs:
        n = max(int(round((r["hi"] - r["lo"]) / pitch)) + 1, 1)
        for k in range(n):
            pos = r["lo"] + k * pitch
            if pos > r["hi"] + 1.0:
                continue
            # a straight through-thickness run standing in for the real
            # bend/leg geometry -- centered on the panel mid-depth and
            # forced to the measured real unit length (correct weight)
            # rather than clamped to the cover-to-cover span, since the
            # true 3D bend direction isn't reconstructable from either
            # view (same reasoning _synthesize_ties already applies to
            # its own simplified corner-tail hook ends).
            if r["axis"] == "v":
                pts = [(r["coord"] - x0, pos - y0, zc - half), (r["coord"] - x0, pos - y0, zc + half)]
            else:
                pts = [(pos - x0, r["coord"] - y0, zc - half), (pos - x0, r["coord"] - y0, zc + half)]
            out.append(Bar3D(pts, dia, "hook", "synthesized"))
    return bars + out


def _merge_dowel_legs(bars: list[Bar3D]) -> list[Bar3D]:
    """Join a face-dowel's protruding leg with its embedded in-plane leg.

    A face-dowel (a circle in the elevation, perpendicular to the panel
    face) only ever gets a straight z-only run in this pipeline -- its
    embedded anchor leg, which runs *in-plane* before bending toward the
    face, is a completely separate double-line bar reconstructed as an
    ordinary v-mesh/h-mesh entry that happens to end at the same (x, y).
    Confirmed on PW-01: the BBS's own "E"/"E1" dowel rows are a 2-segment
    bend (~475mm embedded leg + a ~520-585mm protruding leg); the
    face-dowel path alone only ever captures the protruding leg, quietly
    undercounting each dowel's real length by roughly half. Only merges
    when a same-diameter v-mesh/h-mesh bar's own endpoint lands within
    30mm of the dowel's (x, y) -- real position evidence, not a guess;
    left alone otherwise (confirmed only ~28% of dowels have such a
    candidate at all on PW-01 -- the rest genuinely have no second leg
    detected anywhere, a different, still-open gap).
    """
    dowels = [b for b in bars if b.kind == "face-dowel"]
    others = [b for b in bars if b.kind != "face-dowel"]
    claimed: set[int] = set()
    out: list[Bar3D] = []
    for dw in dowels:
        dx, dy, _ = dw.points[0]
        best: tuple[int, float] | None = None
        for i, leg in enumerate(others):
            if i in claimed or leg.kind not in ("v-mesh", "h-mesh") or leg.diameter != dw.diameter:
                continue
            d = min(math.dist((p[0], p[1]), (dx, dy)) for p in (leg.points[0], leg.points[-1]))
            if d < 30.0 and (best is None or d < best[1]):
                best = (i, d)
        if best is None:
            out.append(dw)
            continue
        i, _ = best
        claimed.add(i)
        leg = others[i]
        leg_pts = list(leg.points)
        if math.dist((leg_pts[-1][0], leg_pts[-1][1]), (dx, dy)) > \
           math.dist((leg_pts[0][0], leg_pts[0][1]), (dx, dy)):
            leg_pts = leg_pts[::-1]
        # the leg's own z is only ever a generic mesh-face fallback, not a
        # real measurement at this specific bar -- re-level it to the
        # dowel's own z1 (a real detected circle depth) so joining the two
        # doesn't fabricate an extra "jump" segment's worth of length that
        # was never actually drawn anywhere.
        z_far, z_near = dw.points[0][2], dw.points[1][2]
        leg_pts = [(p[0], p[1], z_near) for p in leg_pts]
        out.append(Bar3D(leg_pts + [dw.points[0]], dw.diameter, "face-dowel", "section"))
    for i, leg in enumerate(others):
        if i not in claimed:
            out.append(leg)
    return out


def _synthesize_column_ties(bars: list[Bar3D], panel_w: float, panel_h: float,
                            thickness: float) -> list[Bar3D]:
    """Full-cross-section closed tie loops on a column-shaped element.

    A column (tall and narrow -- panel_h at least 4x both panel_w and
    thickness, unlike a wall panel where width/height are comparable)
    confines its main verticals with closed stirrup ties wrapping the
    *whole* cross-section, not a wall's per-boundary-pair core loop. This
    drawing style (confirmed on PC-GF-01) shows each real tie leg only as
    a single flat h-mesh line spanning the width at the panel's mid-depth
    default z -- z_source=="plane-snap" for literally every one of them
    (75/75 on PC-GF-01), meaning none of them ever got real front/back
    depth evidence, unlike genuine field mesh which usually does. That's
    real, evidence-backed position data (not guessed) -- what's missing is
    only the loop's other 3 sides, which the column's own already-known
    cross-section (panel_w, thickness) supplies directly, no callout/pitch
    parsing needed (this drawing's own "-(N) -(T{d})" and zone labels are
    too ambiguous to safely reconstruct exact zone boundaries from; real
    position evidence + known real cross-section is the safer bar to
    clear, same principle as every other synthesis pass in this file).

    Consecutive positions within 20mm are merged into one real tie (a
    ~16mm-apart sub-pair recurs constantly in the raw data -- confirmed
    same z, so not a front/back pair -- almost certainly one tie's main
    leg plus a small hook-closure fragment `chain_bars` didn't join).
    """
    if panel_h < 4 * panel_w or panel_h < 4 * thickness:
        return bars  # not a column-shaped element
    cover = 40.0
    x_lo, x_hi = cover, panel_w - cover
    z_lo, z_hi = cover, thickness - cover
    if x_hi <= x_lo or z_hi <= z_lo:
        return bars

    NO_DEPTH_EVIDENCE = ("plane-snap", "default")
    by_dia: dict[int, list[float]] = {}
    for b in bars:
        if b.kind != "h-mesh" or b.z_source not in NO_DEPTH_EVIDENCE:
            continue
        span = abs(b.points[-1][0] - b.points[0][0])
        if span < 0.7 * (panel_w - 2 * cover):
            continue
        by_dia.setdefault(b.diameter, []).append(b.points[0][1])

    kept: list[Bar3D] = [b for b in bars if not (
        b.kind == "h-mesh" and b.z_source in NO_DEPTH_EVIDENCE
        and b.diameter in by_dia
        and abs(b.points[-1][0] - b.points[0][0]) >= 0.7 * (panel_w - 2 * cover))]
    out: list[Bar3D] = []
    for dia, ys in by_dia.items():
        ys = sorted(ys)
        merged = [ys[0]]
        for y in ys[1:]:
            if y - merged[-1] > 20.0:
                merged.append(y)
        h = 80.0 / math.sqrt(2)
        for y in merged:
            t1 = (x_lo + h, y, z_lo + h)
            t2 = (x_lo + h, y, z_hi - h)
            pts = [t1, (x_lo, y, z_lo), (x_hi, y, z_lo), (x_hi, y, z_hi),
                   (x_lo, y, z_hi), t2]
            out.append(Bar3D(pts, dia, "tie", "synthesized"))
    return kept + out


def _dedupe_near(bars: list[Bar3D]) -> list[Bar3D]:
    """Drop near-duplicate bars: same kind+diameter, both endpoints within
    6mm, length within 5%. Detection and synthesis paths can each emit
    their own copy of one physical bar (e.g. a dashed centerline split
    across offset bins yielding 3 coincident crack bars ~4-6mm apart);
    one physical bar must book its steel exactly once. The tolerance must
    stay under the tightest real separation in these drawings: mesh-face
    z-planes sit as little as 9.6mm apart (33.6 vs 43.2 on PW-GF-09) --
    a 25mm first attempt silently deleted one of each such real pair."""
    kept: list[Bar3D] = []
    for b in bars:
        e0, e1 = b.points[0], b.points[-1]
        lb = sum(math.dist(p, q) for p, q in zip(b.points, b.points[1:]))
        dup = False
        for k in kept:
            if k.kind != b.kind or k.diameter != b.diameter:
                continue
            k0, k1 = k.points[0], k.points[-1]
            if (math.dist(e0, k0) < 6 and math.dist(e1, k1) < 6) or \
               (math.dist(e0, k1) < 6 and math.dist(e1, k0) < 6):
                lk = sum(math.dist(p, q) for p, q in zip(k.points, k.points[1:]))
                if lk and abs(lb - lk) / lk < 0.05:
                    dup = True
                    break
        if not dup:
            kept.append(b)
    return kept


_LABELLED_SINGLE_RE = re.compile(r"(\d+)\s*-\s*T(\d+)[^\d]*CRACK\s*BAR", re.IGNORECASE)


def _synthesize_labelled_singles(bars: list[Bar3D], elev_ents, x0: float, y0: float,
                                 thickness: float, all_ents=None) -> list[Bar3D]:
    """Bars drawn as a single annotation-style centerline, not a to-scale
    double-line outline -- confirmed directly for "N -T{d} ... CRACK BAR"
    callouts: the geometry near each label is a *single* dashed diagonal
    line (multiple short collinear segments, no parallel second rail), so
    pair_lines' gap-width diameter inference structurally cannot see it --
    there's no gap to measure. Merge same-line dashes into full centerlines
    (the same idea as pair_lines' own rail merging, applied to unpaired
    single lines) and take the diameter directly from the label text
    instead of inferring it from geometry that was never drawn to convey it.
    """
    callouts = []
    for e in elev_ents:
        if e.kind not in ("TEXT", "MTEXT"):
            continue
        m = _LABELLED_SINGLE_RE.search(e.text or "")
        if m:
            cx, cy = (e.bbox[0] + e.bbox[2]) / 2, (e.bbox[1] + e.bbox[3]) / 2
            callouts.append((int(m.group(1)), int(m.group(2)), cx, cy))
    # fallback count for lines whose own label sits in ANOTHER view (like
    # tie callouts, crack-bar labels are placed wherever the detail shows;
    # PW-GF-09 keeps 3 of its 4 in the elevation): the modal (count, dia)
    # among crack callouts drawing-wide
    fallback = None
    if all_ents is not None:
        alldp = [(int(m.group(1)), int(m.group(2)))
                 for e in all_ents if e.kind in ("TEXT", "MTEXT")
                 for m in [_LABELLED_SINGLE_RE.search(e.text or "")] if m]
        if alldp:
            fallback = max(set(alldp), key=alldp.count)
    if not callouts and not fallback:
        return bars

    segs = []
    for e in elev_ents:
        if e.layer != "S-RBAR" or e.kind != "LINE":
            continue
        s = _Seg(e.points[0], e.points[1])
        if s.len >= 6.0:
            segs.append(s)

    # diagonal only -- axis-aligned lines are the regular mesh, already
    # handled by the paired double-line path
    rails: dict[tuple, list[_Seg]] = {}
    for s in segs:
        deg = math.degrees(s.angle)
        if deg < 20 or deg > 160 or abs(deg - 90) < 20:
            continue
        rails.setdefault((round(s.angle / 0.02), round(s.noff / 3)), []).append(s)

    merged: list[tuple[float, float, float, float]] = []
    for group in rails.values():
        group.sort(key=lambda s: s.t0)
        angle = group[0].angle
        noff = sum(s.noff for s in group) / len(group)
        cur0, cur1 = group[0].t0, group[0].t1
        for s in group[1:]:
            if s.t0 <= cur1 + 60.0:
                cur1 = max(cur1, s.t1)
            else:
                merged.append((angle, noff, cur0, cur1))
                cur0, cur1 = s.t0, s.t1
        merged.append((angle, noff, cur0, cur1))
    merged = [r for r in merged if r[3] - r[2] >= 300.0]  # drop stray short fragments

    # coalesce near-identical centerlines: the offset-bin key above splits a
    # dashed line whose rail jitters a few mm across two adjacent noff bins,
    # yielding 2-3 slightly-offset copies of the SAME drawn line -- each of
    # which a callout then claimed as a separate bar (observed directly:
    # PW-GF-09's bottom-left crack bar synthesized 3x a few mm apart while
    # the actual X-partner line went unclaimed). Some lines are also drawn
    # as TWO dashed rails a bar-width apart (12mm on PW-GF-09's T12
    # diagonals) -- those are one physical bar too, so the merge distance
    # must cover a rail gap (~2 bar widths), not just binning jitter; the
    # nearest genuinely distinct diagonals sit >500mm apart. Same angle,
    # offset within 40mm, overlapping parametric range = one line.
    merged.sort(key=lambda r: (r[0], r[1]))
    coalesced: list[list[float]] = []
    for angle, noff, t0, t1 in merged:
        for c in coalesced:
            if (abs(c[0] - angle) < 0.02 and abs(c[1] - noff) < 40.0
                    and t0 <= c[3] + 100 and t1 >= c[2] - 100):
                c[2], c[3] = min(c[2], t0), max(c[3], t1)
                break
        else:
            coalesced.append([angle, noff, t0, t1])
    merged = [tuple(c) for c in coalesced]

    # lines: merged centerlines, each annotated with how many bars ALREADY
    # lie on it -- pair_lines does detect some crack bars itself (one
    # mid-plane bar per drawn line), and a callout's count is
    # bars-per-location (front/back face copies of ONE drawn line:
    # "2 -T12 Crack Bar" points at a single diagonal). Claiming `count`
    # different LINES per callout was doubly wrong: it left the X-partner
    # line unclaimed while booking offset-bin duplicates, and it ignored
    # the already-detected copy so steel got double-booked.
    lines = []
    for angle, noff, t0, t1 in merged:
        ux, uy = math.cos(angle), math.sin(angle)
        p0 = (ux * t0 - uy * noff - x0, uy * t0 + ux * noff - y0)
        p1 = (ux * t1 - uy * noff - x0, uy * t1 + ux * noff - y0)
        mx, my = (ux * (t0 + t1) / 2 - uy * noff, uy * (t0 + t1) / 2 + ux * noff)
        lines.append({"p0": p0, "p1": p1, "mid_draw": (mx, my),
                      "have": [], "used": False})
    for b in bars:
        if b.kind != "diagonal":
            continue
        b0, b1 = b.points[0][:2], b.points[-1][:2]
        for ln in lines:
            if (math.dist(b0, ln["p0"]) < 60 and math.dist(b1, ln["p1"]) < 60) or \
               (math.dist(b0, ln["p1"]) < 60 and math.dist(b1, ln["p0"]) < 60):
                ln["have"].append(b)
                break

    # line-centric: each drawn line asks its nearest callout how many bars
    # it represents. (Callout-centric claiming chain-shifted on PW-GF-09:
    # leader labels sit between quadrants, so callouts claimed each
    # other's lines, triple-stacking one and starving another.)
    out: list[Bar3D] = []
    for ln in lines:
        cand = sorted((math.dist(ln["mid_draw"], (ccx, ccy)), count, dia)
                      for count, dia, ccx, ccy in callouts)
        if cand and cand[0][0] <= 1500.0:
            _, count, dia = cand[0]
        elif fallback:
            count, dia = fallback
        else:
            continue
        cover = 30.0
        face_z = [cover + dia / 2, thickness - cover - dia / 2,
                  thickness / 2]
        taken_z = [b.points[0][2] for b in ln["have"]]
        for b in ln["have"]:  # trust the label's diameter over inference
            b.diameter = dia
        need = count - len(ln["have"])
        for z in face_z:
            if need <= 0:
                break
            if any(abs(z - tz) < 10 for tz in taken_z):
                continue
            out.append(Bar3D([(ln["p0"][0], ln["p0"][1], z),
                              (ln["p1"][0], ln["p1"][1], z)],
                             dia, "diagonal", "synthesized"))
            need -= 1
    return bars + out


def reconstruct_panel(name: str, views: list[View]) -> Panel:
    elev = views[0]
    bbox, loops = wall_outline(elev.ents)
    x0, y0, x1, y1 = bbox
    pw, ph = x1 - x0, y1 - y0

    sections = classify_sections(views, pw, ph, bbox)
    thickness = (
        statistics.median([s.thickness for s in sections]) if sections else 160.0
    )

    bars2d = [b for b in extract_bars(elev.ents) if b.length >= 100.0]
    bars2d = _bridge_projecting(bars2d, bbox)

    bars: list[Bar3D] = []
    n_section_z = 0
    zs_seen: list[float] = []
    for b in bars2d:
        dia = snap_diameter(b.diameter)
        if dia is None:
            continue
        orient = _orientation(b)
        r = dia / 2
        zs: list[float] = []
        if orient == "v":
            zs = _z_lookup(sections, "horizontal", b.points[0][0] - x0, r)
        elif orient == "h":
            zs = _z_lookup(sections, "vertical", b.points[0][1] - y0, r)
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

    # Mesh bars the elevation's double-line pairing never independently
    # found at all — not "missing depth", missing entirely, usually because
    # a real bar's rails got outcompeted or absorbed during the pairing of
    # a much denser overlapping mesh nearby. A section cut still shows them
    # as a plain circle (front+back pair) even though nothing in the
    # elevation was ever recognised as a candidate bar there. Every prior
    # use of section data in this function only adds *depth* to a bar the
    # elevation already found; originate a new bar outright when a
    # position/diameter shows a genuine front+back circle pair with no
    # matching elevation bar nearby at all.
    for role, kind, axis_len in (("horizontal", "v-mesh", ph), ("vertical", "h-mesh", pw)):
        covered: dict[int, list[float]] = {}
        for bar in bars:
            if bar.kind != kind:
                continue
            pos = bar.points[0][0] if kind == "v-mesh" else bar.points[0][1]
            covered.setdefault(bar.diameter, []).append(pos)

        hits: dict[int, list[tuple[float, float, int]]] = {}
        for si, s in enumerate(sections):
            if s.role != role:
                continue
            for c, z, r in s.circles:
                dia = snap_diameter(2 * r)
                if dia is not None:
                    hits.setdefault(dia, []).append((c, z, si))

        for dia, pts in hits.items():
            pts.sort()
            clusters: list[list[tuple[float, float, int]]] = []
            for c, z, si in pts:
                if clusters and c - clusters[-1][-1][0] <= 15.0:
                    clusters[-1].append((c, z, si))
                else:
                    clusters.append([(c, z, si)])
            existing = covered.setdefault(dia, [])
            for cl in clusters:
                if len({si for _, _, si in cl}) < 2:
                    continue  # one section's sample alone is too easy to be noise
                cpos = sum(c for c, _, _ in cl) / len(cl)
                if any(abs(cpos - e) <= 40.0 for e in existing):
                    continue  # an elevation bar already covers this position
                zs = _cluster_planes([z for _, z, _ in cl], tol=8.0)
                if len(zs) < 2:
                    continue  # need an agreeing front+back pair, not one stray circle
                for z in zs:
                    n_section_z += 1
                    zs_seen.append(z)
                    pts3 = ([(cpos, 0.0, z), (cpos, axis_len, z)] if kind == "v-mesh"
                            else [(0.0, cpos, z), (axis_len, cpos, z)])
                    bars.append(Bar3D(pts3, dia, kind, "section-origin", cpos))
                existing.append(cpos)

    # A diameter can show more originated positions than physically exist
    # when circles that are real but belong to a *different* category (an
    # edge dowel, not a field mesh bar -- the drawing's own note says
    # dowels are "refer individual mould drawing", i.e. out of scope for
    # this schedule) are geometrically indistinguishable from genuine mesh
    # circles. Confirmed directly on PW-GF-02: 4 T10 positions all
    # independently confirmed by 3 separate sections each (equally strong
    # evidence, no way to rank them against each other on geometry alone)
    # -- but the drawing's own "2 -T10" callout and the official BBS both
    # say only 2 physical bars exist. Use the callout as a hard cap: when
    # one exists and originated positions exceed it, keep the ones
    # furthest from the panel edges (edge-adjacent circles are the more
    # likely dowels) and drop the rest.
    # scan every view, not just the elevation -- this callout is routinely
    # attached to a section view instead (confirmed: PW-GF-02's "2 -T10"
    # sits far outside the elevation's own bbox, in a separate section
    # cluster) since a count callout often labels a detail shown in a
    # section, not the elevation itself
    count_callouts: dict[int, int] = {}
    for v in views:
        for e in v.ents:
            if e.kind not in ("TEXT", "MTEXT"):
                continue
            m = re.search(r"(\d+)\s*-\s*T(\d+)\b", e.text or "")
            if m:
                dia = int(m.group(2))
                count_callouts[dia] = max(count_callouts.get(dia, 0), int(m.group(1)))

    origins_by_dia: dict[int, list[Bar3D]] = {}
    for bar in bars:
        if bar.z_source == "section-origin":
            origins_by_dia.setdefault(bar.diameter, []).append(bar)
    for dia, group in origins_by_dia.items():
        cap = count_callouts.get(dia)
        if cap is None:
            continue
        positions = sorted({b.pos for b in group})
        if len(positions) * 2 <= cap:
            continue
        span = ph if group[0].kind == "v-mesh" else pw
        keep_n = max(cap // 2, 1)
        positions.sort(key=lambda p: -min(p, span - p))  # farthest-from-edge first
        keep = set(positions[:keep_n])
        bars = [b for b in bars if not (b.z_source == "section-origin" and b.diameter == dia and b.pos not in keep)]

    # bars drawn as circles in the elevation are perpendicular to the panel
    # face: the N-series projecting bars. Their protrusion profile (how far
    # out of which face) comes from the matching section.
    profiles = [p for s in sections for p in s.prot]
    for e in elev.ents:
        if e.layer != "S-RBAR" or e.kind != "CIRCLE" or not (2.0 <= e.radius <= 17.0):
            continue
        cx, cy = e.center
        if not (x0 - 5 <= cx <= x1 + 5 and y0 - 5 <= cy <= y1 + 5):
            continue
        dia = snap_diameter(2 * e.radius)
        if dia is None:
            continue
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

    bars = _fold_ubars(bars, sections)
    bars = _synthesize_ties(bars, [e for v in views for e in v.ents],
                            thickness, ph)
    bars = _synthesize_hairpins(bars, elev.ents, thickness, ph)
    bars = _synthesize_labelled_singles(bars, elev.ents, x0, y0, thickness,
                                        [e for v in views for e in v.ents])
    bars = _synthesize_hooks(bars, views, thickness, x0, y0)
    bars = _synthesize_column_ties(bars, pw, ph, thickness)
    bars = _merge_dowel_legs(bars)
    bars = _dedupe_near(bars)

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

    openings = [[(px - x0, py - y0) for px, py in lp] for lp in loops]
    stats = {
        "bars": len(bars),
        "z_from_sections": n_section_z,
        "sections_found": len(sections),
        "z_planes": sorted(round(z, 1) for z in _cluster_planes(zs_seen)) if zs_seen else [],
        "u_bars": sum(1 for b in bars if b.kind == "u-bar"),
        "features": {k: sum(1 for f in features if f.kind == k)
                     for k in ("sleeve", "corbel", "embed", "anchor", "loop")},
    }
    return Panel(name, pw, ph, thickness, openings, bars, stats,
                 mesh_families(bars), features)


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
