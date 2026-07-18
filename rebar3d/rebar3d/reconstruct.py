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


def _synthesize_ties(bars: list[Bar3D], elev_ents, thickness: float,
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
    callouts = []
    for e in elev_ents:
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

    # pair adjacent positions into tie stacks (tie core is ~200mm wide,
    # so partners sit within ~160mm of each other), greedily left to right
    xs = sorted(main)
    out: list[Bar3D] = []
    i = 0
    while i < len(xs) - 1:
        if xs[i + 1] - xs[i] <= 160.0:
            x_lo, x_hi = xs[i] - cover, xs[i + 1] + cover
            runs = intersect(merged(main[xs[i]]), merged(main[xs[i + 1]]))
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
            i += 2  # both positions consumed by this stack
        else:
            i += 1
    return bars + out


_UBAR_PITCH_RE = re.compile(r"T(\d+)\s*UBAR\s*@\s*(\d+)\s*mm", re.IGNORECASE)


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
    when a geometry-detected u-bar already sits within 120mm.
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

    web_lo, web_hi = cover, thickness - cover
    out: list[Bar3D] = []
    for x, group in by_x.items():
        zs = {round(b.points[0][2], 0) for b in group}
        if len(zs) < 2:
            continue  # hairpins close a two-face pair; single-face has none
        y0 = min(p[1] for b in group for p in b.points)
        y1 = max(p[1] for b in group for p in b.points)
        for y_end, leg_dir in ((y0, 1.0), (y1, -1.0)):
            if any(abs(ex - x) < 120 and abs(ey - y_end) < 200 for ex, ey in existing):
                continue
            if not (0 <= y_end <= panel_h):
                continue  # a projecting stub's end isn't a panel free edge
            y_end = min(max(y_end, cover), panel_h - cover)
            leg = 400.0 * leg_dir
            if not (0 <= y_end + leg <= panel_h):
                continue
            pts = [(x, y_end + leg, web_lo), (x, y_end, web_lo),
                   (x, y_end, web_hi), (x, y_end + leg, web_hi)]
            out.append(Bar3D(pts, dia, "u-bar", "synthesized"))
    return bars + out


_LABELLED_SINGLE_RE = re.compile(r"(\d+)\s*-\s*T(\d+)[^\d]*CRACK\s*BAR", re.IGNORECASE)


def _synthesize_labelled_singles(bars: list[Bar3D], elev_ents, x0: float, y0: float, thickness: float) -> list[Bar3D]:
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
    if not callouts:
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

    used = [False] * len(merged)
    out: list[Bar3D] = []
    for count, dia, ccx, ccy in callouts:
        cand = []
        for i, (angle, noff, t0, t1) in enumerate(merged):
            if used[i]:
                continue
            ux, uy = math.cos(angle), math.sin(angle)
            mt = (t0 + t1) / 2
            mx, my = ux * mt - uy * noff, uy * mt + ux * noff
            cand.append((math.dist((mx, my), (ccx, ccy)), i))
        cand.sort()
        for d, i in cand[:count]:
            if d > 1200.0:
                continue
            used[i] = True
            angle, noff, t0, t1 = merged[i]
            ux, uy = math.cos(angle), math.sin(angle)
            p0 = (ux * t0 - uy * noff - x0, uy * t0 + ux * noff - y0)
            p1 = (ux * t1 - uy * noff - x0, uy * t1 + ux * noff - y0)
            z = thickness / 2
            out.append(Bar3D([(p0[0], p0[1], z), (p1[0], p1[1], z)], dia, "diagonal", "synthesized"))
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
    bars = _synthesize_ties(bars, elev.ents, thickness, ph)
    bars = _synthesize_hairpins(bars, elev.ents, thickness, ph)
    bars = _synthesize_labelled_singles(bars, elev.ents, x0, y0, thickness)

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
