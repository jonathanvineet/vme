"""Extract real bar geometry (position + length + bend shape) from an (R)
rebar-layout DWG's elevation view, for the 3D viewer.

Fresh, independent code (does not import rebar3d - reference only). This
module was rebuilt (2026-07) to follow rebar3d's proven two-stage
architecture instead of bbs_reconcile's original single-pass one, after
direct measurement (geo_reconcile.py) showed the original approach was
still ~30-50% under the true schedule weight even with generous tuning:

  1. Merge raw LINE fragments into "rails" using a conservative, tight
     gap (rebar3d found 60mm safe here) BEFORE anything is typed by
     diameter - this stage doesn't yet know which fragments belong to
     which bar, so it must not risk bridging across unrelated geometry.
  2. Pair rails whose perpendicular gap matches a standard diameter into
     straight Bar pieces (sub-range claiming, xdata-set-gated - see
     _pair_rails).
  3. NOW that pieces are typed by diameter, do a SECOND merge pass
     across same-diameter, same-line Bar pieces using a diameter-
     dependent gap (250mm for dia>=16mm edge/beam bars - these get
     trimmed by crossing detail bars into fragments up to ~200mm apart;
     60mm for lighter mesh, where a real gap that size is often a
     genuinely separate bar across an opening, not a trim artifact).
  4. Pair concentric ARC entities (bend/hook radii) into bend-centerline
     pieces the same way lines are paired.
  5. Chain straight + bend pieces whose endpoints coincide and whose
     diameter matches the chain's *seed* piece (not a running average,
     which can drift across two adjacent standard sizes one small hop
     at a time) into full multi-vertex bar shapes - this is what lets
     real U-bars/hooks be reconstructed from drawn geometry instead of
     only synthesized from schedule data (see bent_bars.py, still used
     as a fallback for shapes no chain reaches).

This module ALSO keeps an addition rebar3d's own extractor doesn't have:
every S-RBAR LINE carries REVIT xdata tagging which Revit "Rebar Set"
element it came from (confirmed by direct inspection - one Revit element
covers a whole bar family, e.g. all 8 instances of one schedule mark).
Rail merging and pairing prefer matches within the same Revit set,
which is an extra, independent guard against cross-contaminating two
unrelated nearby bar families - on top of, not instead of, rebar3d's
own diameter-continuity gating.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

from dxf_cache import dwg_to_dxf

STD_DIAMETERS = [8, 10, 12, 16, 20, 25, 32]
DIA_TOL = 2.0
COLLINEAR_ANGLE_TOL = 0.03   # radians
COLLINEAR_OFFSET_TOL = 3.0   # mm perpendicular offset to merge into same rail
MERGE_GAP = 900.0              # mm gap allowed to bridge fragments of the same RAW rail
                               # BEFORE diameter is known. rebar3d's own extract.py uses
                               # a tight 60mm here (relying on its diameter-aware second
                               # pass for the rest) - tried that directly on this drawing
                               # set and it regressed badly (geo_reconcile.py weight delta
                               # went from -22/-53% back to -74/-97%): this set's crossing
                               # trims leave gaps the xdata-grouped rail merge needs 900mm
                               # to bridge, evidently a different crossing pitch/pattern
                               # than rebar3d's source drawings. Keep the value that's
                               # actually measured to work for these DWGs, not rebar3d's.
POST_MERGE_GAP_HEAVY = 250.0  # mm - same-diameter/same-line Bar fragments, dia>=16mm
POST_MERGE_GAP_LIGHT = 60.0   # mm - same-diameter/same-line Bar fragments, dia<16mm
CHAIN_ENDPOINT_TOL = 4.0      # mm - endpoint coincidence to chain two pieces together
CHAIN_DIA_TOL = 1.9           # mm - kept under the 2mm gap between adjacent standard
                               # sizes so a chain can't drift T8->T10->T12 one hop at a time
MIN_BAR_LEN = 60.0            # mm - below this, a "bar" is almost always a
                               # crossing-trim artifact or witness-line noise,
                               # not a real reinforcement bar
MIN_OVERLAP_FRAC = 0.5
CLUSTER_GAP = 300.0          # mm gap to treat two wall regions as separate views


def snap_diameter(gap: float) -> float | None:
    best = min(STD_DIAMETERS, key=lambda d: abs(d - gap))
    return float(best) if abs(best - gap) <= DIA_TOL else None


@dataclass
class Seg:
    x0: float
    y0: float
    x1: float
    y1: float
    grp: object = None   # Revit rebar-set id from REVIT xdata, or None

    @property
    def length(self):
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    @property
    def angle(self):
        return math.atan2(self.y1 - self.y0, self.x1 - self.x0) % math.pi


def _revit_set_id(entity) -> str | None:
    """Revit's DWG export stamps every line with REVIT xdata carrying the
    id of the Revit "Rebar Set" element it came from (one Revit element
    can represent many physical parallel bars at a pitch, e.g. a whole
    mesh layer - confirmed by direct inspection: grouping ~10000 raw
    S-RBAR LINE fragments in one panel by this id split them into ~43
    clean subsets, each spanning a narrow diameter/length range that
    lines up with one schedule mark's bar family. This is the single
    biggest lever for untangling dense-mesh crossing fragmentation:
    pairing/merging WITHIN one Revit set's lines avoids ever confusing
    one bar family's edges with an unrelated nearby family's, which was
    the dominant source of both under- and over-detection before this.
    """
    if not entity.xdata:
        return None
    try:
        tags = entity.xdata.get("REVIT")
    except Exception:
        return None
    cur_code = None
    for t in tags:
        if t.code == 1070:
            cur_code = t.value
        elif t.code == 1000 and cur_code == 1:
            return t.value
    return None


@dataclass
class Bar:
    dia_mm: float
    x0: float
    y0: float
    x1: float
    y1: float
    z0: float = 0.0
    z1: float = 0.0
    z_source: str = "none"   # "section" (measured) or "none" (unknown depth, left at 0)
    mid_pts: list = field(default_factory=list)   # interior (x,y) vertices for a
                                                    # real chained bend shape (empty
                                                    # for a plain straight bar)
    chained: bool = False    # True = this shape was assembled from real drawn
                              # line+arc geometry (chain_bars), not schedule synthesis
    from_arc: bool = False   # True = this piece came from _pair_arcs (a real drawn
                              # bend), used to gate chain_bars - see chain_bars docstring

    @property
    def points(self) -> list[tuple[float, float]]:
        return [(self.x0, self.y0), *self.mid_pts, (self.x1, self.y1)]


def _bbox(x0, y0, x1, y1):
    return (min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1))


def _cluster_regions(boxes, gap=CLUSTER_GAP):
    n = len(boxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    def overlaps(a, b):
        return not (a[1] + gap < b[0] or b[1] + gap < a[0] or a[3] + gap < b[2] or b[3] + gap < a[2])

    for i in range(n):
        for j in range(i + 1, n):
            if overlaps(boxes[i], boxes[j]):
                union(i, j)

    from collections import defaultdict
    clusters = defaultdict(list)
    for i, b in enumerate(boxes):
        clusters[find(i)].append(b)
    return list(clusters.values())


def _find_elevation_bbox(msp) -> tuple[float, float, float, float] | None:
    boxes = []
    for e in msp:
        if e.dxf.layer == "A-WALL" and e.dxftype() == "LINE":
            x0, y0, _ = e.dxf.start
            x1, y1, _ = e.dxf.end
            boxes.append(_bbox(x0, y0, x1, y1))
    if not boxes:
        return None
    clusters = _cluster_regions(boxes)

    def cluster_bbox(v):
        return (min(b[0] for b in v), max(b[1] for b in v), min(b[2] for b in v), max(b[3] for b in v))

    def area(v):
        x0, x1, y0, y1 = cluster_bbox(v)
        return (x1 - x0) * (y1 - y0)

    best = max(clusters, key=area)
    return cluster_bbox(best)


def _rail_key(seg: Seg):
    a = seg.angle
    # normalize direction, then perpendicular offset from origin
    nx, ny = -math.sin(a), math.cos(a)
    ox = seg.x0 * nx + seg.y0 * ny
    return a, ox


def _merge_rails(segs: list[Seg]) -> list[dict]:
    """Group near-collinear segments and merge overlapping/near ones along
    their shared direction into continuous rails.

    Segments only join the same rail if they also share the same Revit
    rebar-set id (see _revit_set_id) when both have one - this keeps two
    unrelated bar families that happen to sit at a coincidentally similar
    offset from being merged into one bogus rail (the dominant source of
    both under- and over-detection before this id was found)."""
    used = [False] * len(segs)
    rails = []
    items = [(_rail_key(s), s) for s in segs]
    for i, ((a_i, o_i), s_i) in enumerate(items):
        if used[i]:
            continue
        group = [i]
        used[i] = True
        for j in range(i + 1, len(items)):
            if used[j]:
                continue
            (a_j, o_j), s_j = items[j]
            da = min(abs(a_i - a_j), math.pi - abs(a_i - a_j))
            if da <= COLLINEAR_ANGLE_TOL and abs(o_i - o_j) <= COLLINEAR_OFFSET_TOL \
                    and (s_i.grp is None or s_j.grp is None or s_i.grp == s_j.grp):
                group.append(j)
                used[j] = True
        # merge along direction: project all endpoints onto the direction vector
        dx, dy = math.cos(a_i), math.sin(a_i)
        pts = []
        for k in group:
            s = segs[k]
            pts.append((s.x0, s.y0))
            pts.append((s.x1, s.y1))
        # project onto the direction vector in absolute coordinates (must
        # match the absolute-frame projection used later in pt()/_pair_rails)
        proj = sorted((p[0] * dx + p[1] * dy, p) for p in pts)
        # collapse into intervals allowing MERGE_GAP bridging
        intervals = []
        cur_lo, cur_hi = proj[0][0], proj[0][0]
        cur_lo_pt, cur_hi_pt = proj[0][1], proj[0][1]
        for t, p in proj[1:]:
            if t - cur_hi <= MERGE_GAP:
                cur_hi = max(cur_hi, t)
                if t == cur_hi:
                    cur_hi_pt = p
            else:
                intervals.append((cur_lo, cur_hi, cur_lo_pt, cur_hi_pt))
                cur_lo, cur_hi, cur_lo_pt, cur_hi_pt = t, t, p, p
        intervals.append((cur_lo, cur_hi, cur_lo_pt, cur_hi_pt))
        rail_grp = s_i.grp
        for lo, hi, plo, phi in intervals:
            if hi - lo < 6:
                continue
            rails.append({"angle": a_i, "offset": o_i, "lo": lo, "hi": hi, "p0": plo, "p1": phi, "grp": rail_grp})
    return rails


def _subtract(intervals: list[tuple[float, float]], lo: float, hi: float) -> list[tuple[float, float]]:
    out = []
    for a, b in intervals:
        if b <= lo or a >= hi:
            out.append((a, b))
            continue
        if a < lo:
            out.append((a, lo))
        if b > hi:
            out.append((hi, b))
    return out


def _pair_rails(rails: list[dict]) -> list[Bar]:
    """Pair rails into bars using sub-range (not whole-rail) claims, and a
    global greedy longest-overlap-first order.

    Two things fragment a physical bar's two edges asymmetrically:
    crossing-bar trims (one edge merges long, the other stays broken up),
    and drafting noise that puts a second, spurious, similarly-spaced
    rail near the true partner (a nearby unrelated bar or witness line
    whose offset gap also happens to snap to *some* standard diameter).
    Claiming matches in arbitrary order lets a short spurious match grab
    a rail's free space before its true long partner is considered,
    starving the real bar down to a stub. Processing the single longest
    available overlap first, globally, across every candidate pair
    (via a lazily-validated max-heap) ensures the strongest, most
    confident pairing always wins first claim on any rail's length.
    """
    import heapq

    n = len(rails)
    free = [[(r["lo"], r["hi"])] for r in rails]

    order = sorted(range(n), key=lambda i: (round(rails[i]["angle"], 3), rails[i]["offset"]))
    pairs = []  # (i, j, dia)
    max_dia = max(STD_DIAMETERS) + DIA_TOL
    for oi, i in enumerate(order):
        ri = rails[i]
        for oj in range(oi + 1, len(order)):
            j = order[oj]
            rj = rails[j]
            if rj["offset"] - ri["offset"] > max_dia:
                break
            da = min(abs(ri["angle"] - rj["angle"]), math.pi - abs(ri["angle"] - rj["angle"]))
            if da > COLLINEAR_ANGLE_TOL:
                continue
            dia = snap_diameter(abs(ri["offset"] - rj["offset"]))
            if dia is None:
                continue
            pairs.append((i, j, dia))

    def build_bar(i, j, dia, lo, hi):
        ri, rj = rails[i], rails[j]
        a = ri["angle"]
        dx, dy = math.cos(a), math.sin(a)
        mid_off = (ri["offset"] + rj["offset"]) / 2.0
        nx, ny = -math.sin(a), math.cos(a)
        ref = ri["p0"]
        ref_t = ref[0] * dx + ref[1] * dy

        def pt(t):
            base_x = ref[0] + (t - ref_t) * dx
            base_y = ref[1] + (t - ref_t) * dy
            cur_off = base_x * nx + base_y * ny
            corr = mid_off - cur_off
            return base_x + corr * nx, base_y + corr * ny

        x0, y0 = pt(lo)
        x1, y1 = pt(hi)
        return Bar(dia, x0, y0, x1, y1)

    def best_overlap(i, j):
        best = None
        for a, b in free[i]:
            for c, d in free[j]:
                lo, hi = max(a, c), min(b, d)
                if hi - lo > MIN_BAR_LEN and (best is None or hi - lo > best[1] - best[0]):
                    best = (lo, hi)
        return best

    def priority(i, j):
        # same-Revit-set pairs always win over cross-set pairs of equal or
        # even somewhat greater length - a cross-set match is only ever a
        # fallback for whatever free rail space no same-set partner claims
        gi, gj = rails[i]["grp"], rails[j]["grp"]
        return 0 if (gi is not None and gi == gj) else 1

    heap = []
    for pidx, (i, j, dia) in enumerate(pairs):
        ov = best_overlap(i, j)
        if ov:
            heapq.heappush(heap, (priority(i, j), -(ov[1] - ov[0]), pidx, ov[0], ov[1]))

    bars = []
    while heap:
        prio, neg_len, pidx, lo, hi = heapq.heappop(heap)
        i, j, dia = pairs[pidx]
        # lazy validation: free space may have shrunk since this was pushed
        fresh = best_overlap(i, j)
        if fresh is None:
            continue
        flo, fhi = fresh
        if fhi - flo < hi - lo:
            heapq.heappush(heap, (prio, -(fhi - flo), pidx, flo, fhi))
            continue
        free[i] = _subtract(free[i], flo, fhi)
        free[j] = _subtract(free[j], flo, fhi)
        bars.append(build_bar(i, j, dia, flo, fhi))
        nxt = best_overlap(i, j)
        if nxt:
            heapq.heappush(heap, (prio, -(nxt[1] - nxt[0]), pidx, nxt[0], nxt[1]))
    return bars


def _merge_collinear_bars(bars: list[Bar]) -> list[Bar]:
    """Second merge pass, run AFTER pairing (so diameter is known) - bridges
    same-diameter fragments of the same physical straight bar using a
    diameter-dependent gap. Ported from rebar3d's extract.py::_merge_collinear
    (confirmed there on real edge-beam bars: a 5.14m T20 bar was recovered
    from raw geometry as three 0.2-1.4m pieces with ~200mm crossing-trim
    gaps between them - a flat tight gap misses this, a flat loose gap
    risks bridging unrelated light-mesh bars across genuine openings)."""
    straight = [b for b in bars if not b.mid_pts]
    other = [b for b in bars if b.mid_pts]
    groups: dict[tuple, list[Bar]] = {}
    for b in straight:
        s = Seg(b.x0, b.y0, b.x1, b.y1)
        key = (round(s.angle / 0.005), round(_rail_key(s)[1] / COLLINEAR_OFFSET_TOL), round(b.dia_mm))
        groups.setdefault(key, []).append(b)

    merged: list[Bar] = []
    for (ak, ok, dk), group in groups.items():
        s0 = Seg(group[0].x0, group[0].y0, group[0].x1, group[0].y1)
        ux, uy = math.cos(s0.angle), math.sin(s0.angle)
        _, noff = _rail_key(s0)
        ivs = []
        for b in group:
            t0 = b.x0 * ux + b.y0 * uy
            t1 = b.x1 * ux + b.y1 * uy
            ivs.append((min(t0, t1), max(t0, t1)))
        ivs.sort()
        gap_tol = POST_MERGE_GAP_HEAVY if dk >= 16 else POST_MERGE_GAP_LIGHT
        cur0, cur1 = ivs[0]
        out = []
        for t0, t1 in ivs[1:]:
            if t0 <= cur1 + gap_tol:
                cur1 = max(cur1, t1)
            else:
                out.append((cur0, cur1))
                cur0, cur1 = t0, t1
        out.append((cur0, cur1))
        for t0, t1 in out:
            x0, y0 = ux * t0 - uy * noff, uy * t0 + ux * noff
            x1, y1 = ux * t1 - uy * noff, uy * t1 + ux * noff
            merged.append(Bar(float(dk), x0, y0, x1, y1))
    return merged + other


def _pair_arcs(msp, elev_bbox, margin: float = 50.0) -> list[Bar]:
    """Pair concentric ARC entities on S-RBAR (bend/hook radii) into bend
    centerline pieces - real drawn bends, not schedule-synthesized shapes.
    Ported from rebar3d's extract.py::pair_arcs."""
    ex0, ex1, ey0, ey1 = elev_bbox
    arcs = []
    for e in msp:
        if e.dxftype() != "ARC" or e.dxf.layer != "S-RBAR":
            continue
        cx, cy, _ = e.dxf.center
        if not (ex0 - margin <= cx <= ex1 + margin and ey0 - margin <= cy <= ey1 + margin):
            continue
        if e.dxf.radius <= 1.0:
            continue
        arcs.append(e)

    used = [False] * len(arcs)
    out = []
    for i, a in enumerate(arcs):
        if used[i]:
            continue
        acx, acy, _ = a.dxf.center
        for j in range(i + 1, len(arcs)):
            if used[j]:
                continue
            b = arcs[j]
            bcx, bcy, _ = b.dxf.center
            if math.hypot(acx - bcx, acy - bcy) > 2.0:
                continue
            gap = abs(a.dxf.radius - b.dxf.radius)
            dia = snap_diameter(gap)
            if dia is None:
                continue
            da = (a.dxf.start_angle - b.dxf.start_angle) % 360
            if 15 < da < 345:
                continue
            used[i] = used[j] = True
            mid_r = (a.dxf.radius + b.dxf.radius) / 2.0
            a0 = math.radians(a.dxf.start_angle)
            a1 = math.radians(a.dxf.end_angle)
            if a1 <= a0:
                a1 += 2 * math.pi
            n = 8
            pts = [
                (acx + mid_r * math.cos(a0 + (a1 - a0) * k / n),
                 acy + mid_r * math.sin(a0 + (a1 - a0) * k / n))
                for k in range(n + 1)
            ]
            out.append(Bar(dia, pts[0][0], pts[0][1], pts[-1][0], pts[-1][1],
                            mid_pts=pts[1:-1], chained=True, from_arc=True))
            break
    return out


def chain_bars(bars: list[Bar], tol: float = CHAIN_ENDPOINT_TOL, tol_dia: float = CHAIN_DIA_TOL) -> list[Bar]:
    """Join straight/arc bar pieces whose endpoints coincide into full
    multi-vertex bar shapes (real U-bars, hooks, L/Z-bends - not schedule
    synthesis). Ported from rebar3d's extract.py::chain_bars.

    Chains only extend to a piece whose diameter is close to the chain's
    *seed* piece, not a running average: in a dense mesh, unrelated bars
    of different diameters routinely end at the same point (e.g. a T20 and
    a T12 both terminating at the same opening edge), and gating against a
    drifting average lets a chain hop T8->T10->T12 one small step at a
    time even though adjacent standard sizes are only 2mm apart. tol_dia
    is kept under that 2mm floor.
    """
    used = [False] * len(bars)
    out = []
    for i, b in enumerate(bars):
        if used[i]:
            continue
        used[i] = True
        pts = list(b.points)
        seed_dia = b.dia_mm
        has_arc = b.from_arc
        dias_w = [(b.dia_mm, max(_poly_len(pts), 1e-9))]
        grew = True
        while grew:
            grew = False
            for j, c in enumerate(bars):
                if used[j] or abs(c.dia_mm - seed_dia) > tol_dia:
                    continue
                # Only ever fuse through a REAL drawn bend (an arc piece) -
                # in a dense mesh, unrelated straight bars of the same
                # diameter routinely terminate at the same grid
                # intersection point, and welding two of THOSE together on
                # endpoint proximity alone silently fabricates a bogus bent
                # shape out of two real, separate straight bars (confirmed:
                # this was the actual cause of a net weight regression when
                # first tried unrestricted - real detected length vanished
                # into "bent" candidates that then failed to match any
                # schedule row and were dropped). Same-line straight
                # reconnection is already handled safely by
                # _merge_collinear_bars, which requires matching offset,
                # not just a touching endpoint.
                if not (has_arc or c.from_arc):
                    continue
                cpts = c.points
                c0, c1 = cpts[0], cpts[-1]
                if math.hypot(pts[-1][0] - c0[0], pts[-1][1] - c0[1]) <= tol:
                    pts = pts + cpts[1:]
                elif math.hypot(pts[-1][0] - c1[0], pts[-1][1] - c1[1]) <= tol:
                    pts = pts + cpts[-2::-1]
                elif math.hypot(pts[0][0] - c1[0], pts[0][1] - c1[1]) <= tol:
                    pts = cpts[:-1] + pts
                elif math.hypot(pts[0][0] - c0[0], pts[0][1] - c0[1]) <= tol:
                    pts = cpts[::-1][:-1] + pts
                else:
                    continue
                used[j] = True
                has_arc = has_arc or c.from_arc
                dias_w.append((c.dia_mm, max(_poly_len(cpts), 1e-9)))
                grew = True
        dia = sum(d * w for d, w in dias_w) / sum(w for _, w in dias_w)
        pts = _simplify_collinear(pts)
        out.append(Bar(dia, pts[0][0], pts[0][1], pts[-1][0], pts[-1][1],
                        mid_pts=pts[1:-1], chained=len(pts) > 2, from_arc=has_arc))
    return out


def _simplify_collinear(pts: list[tuple[float, float]], angle_tol: float = 0.02) -> list[tuple[float, float]]:
    """Drop interior vertices where the chain doesn't actually bend - two
    straight pieces chained end-to-end along the same line (e.g. leftover
    fragments _merge_collinear_bars didn't happen to combine first) would
    otherwise show up as a spurious "bent" shape with a pointless kink,
    losing Z-depth eligibility for what is really still a plain straight
    bar."""
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = pts[i][0] - out[-1][0], pts[i][1] - out[-1][1]
        bx, by = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        if la < 1e-9 or lb < 1e-9:
            continue
        cross = (ax * by - ay * bx) / (la * lb)
        dot = (ax * bx + ay * by) / (la * lb)
        if abs(cross) < angle_tol and dot > 0:
            continue  # collinear continuation, not a real bend
        out.append(pts[i])
    out.append(pts[-1])
    return out


def _poly_len(pts: list[tuple[float, float]]) -> float:
    return sum(math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]) for k in range(len(pts) - 1))


SECTION_POS_TOL = 60.0   # mm tolerance matching an elevation bar's position to section evidence


def _find_section_clusters(msp, elev_bbox):
    """Vertical and horizontal section-cut views elsewhere on the sheet.

    Revit registers these to the elevation by sharing its exact Y range
    (vertical cuts, showing depth vs height) or matching its X span
    (horizontal cuts, showing depth vs width) - see module docstring.
    Each carries real circle cross-sections of the bars running through
    that cut, which is the only real evidence of front/back depth: an
    elevation is a straight-on 2D projection where front and back bars
    at the same (x,y) draw as literally the same line, so depth cannot
    be recovered from the elevation alone.
    """
    ex0, ex1, ey0, ey1 = elev_bbox
    ew, eh = ex1 - ex0, ey1 - ey0

    boxes = []
    for e in msp:
        if e.dxf.layer == "A-WALL" and e.dxftype() == "LINE":
            x0, y0, _ = e.dxf.start
            x1, y1, _ = e.dxf.end
            boxes.append(_bbox(x0, y0, x1, y1))
    clusters = _cluster_regions(boxes)

    vertical, horizontal = [], []
    for v in clusters:
        cx0 = min(b[0] for b in v); cx1 = max(b[1] for b in v)
        cy0 = min(b[2] for b in v); cy1 = max(b[3] for b in v)
        cw, ch = cx1 - cx0, cy1 - cy0
        if cx0 >= ex0 - 1 and cx1 <= ex1 + 1 and cy0 >= ey0 - 1 and cy1 <= ey1 + 1:
            continue  # part of the elevation itself
        # vertical section: matches elevation's Y range, much narrower than it's tall
        if abs(cy0 - ey0) < SECTION_POS_TOL and abs(cy1 - ey1) < SECTION_POS_TOL and cw < 0.3 * eh:
            vertical.append((cx0, cx1, cy0, cy1))
        # horizontal section: matches elevation's width, much shorter than it's wide
        elif abs(cw - ew) < SECTION_POS_TOL * 3 and ch < 0.3 * ew:
            horizontal.append((cx0, cx1, cy0, cy1))
    return vertical, horizontal


def _section_circles(msp, bbox):
    x0, x1, y0, y1 = bbox
    out = []
    for e in msp:
        if e.dxftype() != "CIRCLE" or e.dxf.layer != "S-RBAR":
            continue
        cx, cy, _ = e.dxf.center
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            dia = snap_diameter(e.dxf.radius * 2)
            if dia is not None:
                out.append((cx, cy, dia))
    return out


def _build_z_evidence(msp, vertical_clusters, horizontal_clusters):
    """Returns (h_evidence, v_evidence, thickness_mm).

    h_evidence: dict[(round(y/30), dia)] -> list of depth fractions (0..1),
      used for HORIZONTAL bars (their Z varies along Y, sampled by vertical cuts).
    v_evidence: dict[(round(elevation_x/30), dia)] -> list of depth fractions,
      used for VERTICAL bars (their Z varies along X, sampled by horizontal cuts).
    thickness_mm: measured wall thickness (average cluster depth-axis span).
    """
    h_evidence: dict = {}
    thicknesses = []
    for (cx0, cx1, cy0, cy1) in vertical_clusters:
        w = cx1 - cx0
        if w <= 0:
            continue
        thicknesses.append(w)
        for cx, cy, dia in _section_circles(msp, (cx0, cx1, cy0, cy1)):
            frac = (cx - cx0) / w
            h_evidence.setdefault((round(cy / 30), dia), []).append(frac)

    v_evidence: dict = {}
    for (cx0, cx1, cy0, cy1) in horizontal_clusters:
        h = cy1 - cy0
        if h <= 0:
            continue
        thicknesses.append(h)
        # elevation_x isn't known here; caller remaps using elevation bbox + this cluster's own bbox
        for cx, cy, dia in _section_circles(msp, (cx0, cx1, cy0, cy1)):
            frac = (cy - cy0) / h
            v_evidence.setdefault((cx0, cx1, round(cx / 30), dia), []).append(frac)

    thickness_mm = sum(thicknesses) / len(thicknesses) if thicknesses else 150.0
    return h_evidence, v_evidence, thickness_mm


def _remap_v_evidence(v_evidence_raw, elev_bbox):
    """Horizontal-cut clusters live at their own sheet position; their local
    X only means something once rescaled onto the elevation's X span
    (same physical width, just drawn elsewhere on the page)."""
    ex0, ex1, _, _ = elev_bbox
    ew = ex1 - ex0
    out: dict = {}
    for (cx0, cx1, xb, dia), fracs in v_evidence_raw.items():
        cw = cx1 - cx0
        if cw <= 0:
            continue
        local_x = xb * 30  # undo the rounding bucket back to an approx local x
        elev_x = ex0 + (local_x - cx0) / cw * ew
        out.setdefault((round(elev_x / 30), dia), []).extend(fracs)
    return out


def _depth_pair(fracs: list[float]) -> tuple[float, float | None]:
    """Given pooled depth fractions for one (position, diameter), return
    (front_frac, back_frac_or_None) - the two mesh faces if evidence shows
    two distinct clusters, else a single value."""
    if not fracs:
        return 0.5, None
    fracs = sorted(fracs)
    lo_group = [f for f in fracs if f < 0.5]
    hi_group = [f for f in fracs if f >= 0.5]
    if lo_group and hi_group:
        return sum(lo_group) / len(lo_group), sum(hi_group) / len(hi_group)
    return sum(fracs) / len(fracs), None


def _assign_z(bars: list[Bar], h_evidence, v_evidence, thickness_mm: float) -> list[Bar]:
    out = []
    for b in bars:
        angle = math.atan2(b.y1 - b.y0, b.x1 - b.x0) % math.pi
        is_horizontal = angle < 0.05 or angle > math.pi - 0.05
        is_vertical = abs(angle - math.pi / 2) < 0.05

        fracs = None
        if is_horizontal:
            ymid = round((b.y0 + b.y1) / 2 / 30)
            for dy in (0, -1, 1, -2, 2):
                key = (ymid + dy, b.dia_mm)
                if key in h_evidence:
                    fracs = h_evidence[key]
                    break
        elif is_vertical:
            xmid = round((b.x0 + b.x1) / 2 / 30)
            for dx in (0, -1, 1, -2, 2):
                key = (xmid + dx, b.dia_mm)
                if key in v_evidence:
                    fracs = v_evidence[key]
                    break

        if not fracs:
            out.append(b)  # no depth evidence - leave at z=0, flagged via z_source
            continue

        f_front, f_back = _depth_pair(fracs)
        z_front = (f_front - 0.5) * thickness_mm
        out.append(Bar(b.dia_mm, b.x0, b.y0, b.x1, b.y1, z_front, z_front, "section"))
        if f_back is not None:
            z_back = (f_back - 0.5) * thickness_mm
            out.append(Bar(b.dia_mm, b.x0, b.y0, b.x1, b.y1, z_back, z_back, "section"))
    return out


def mirror_fill_diagonals(bars: list[Bar], width_mm: float, tol: float = 250.0) -> list[Bar]:
    """Diagonal (crack) bars at symmetric openings are standard practice
    on both sides in these panels, but the elevation's own line pairing
    only reliably found one side's diagonals in spot checks (confirmed
    directly: PW-GF-02's detected T16 diagonals clustered entirely in
    the x=1600-3300 range, nothing near the opening's other corners -
    a real detection gap, not a drafting asymmetry). Mirror any
    diagonal bar across the panel's vertical centerline and add the
    mirror only where no matching bar already exists there (same
    diameter, position within `tol`) - so genuinely-detected symmetric
    pairs are left untouched and only real gaps get filled.
    """
    def is_diagonal(b):
        ang = math.degrees(math.atan2(b.y1 - b.y0, b.x1 - b.x0)) % 180
        return 20 < ang < 160 and not (80 < ang < 100)

    diagonals = [b for b in bars if is_diagonal(b)]
    added = []
    for b in diagonals:
        mx0, mx1 = width_mm - b.x0, width_mm - b.x1
        bx_lo, bx_hi = min(mx0, mx1), max(mx0, mx1)
        by_lo, by_hi = min(b.y0, b.y1), max(b.y0, b.y1)
        match = False
        for c in diagonals:
            if abs(c.dia_mm - b.dia_mm) > 0.5:
                continue
            cx_lo, cx_hi = min(c.x0, c.x1), max(c.x0, c.x1)
            cy_lo, cy_hi = min(c.y0, c.y1), max(c.y0, c.y1)
            if abs(cx_lo - bx_lo) < tol and abs(cx_hi - bx_hi) < tol and abs(cy_lo - by_lo) < tol and abs(cy_hi - by_hi) < tol:
                match = True
                break
        if not match:
            added.append(Bar(b.dia_mm, mx0, b.y0, mx1, b.y1, b.z0, b.z1, "mirrored"))
    return bars + added


def extract_bars(dwg_path: Path) -> tuple[list[Bar], tuple[float, float, float, float] | None]:
    dxf_path = dwg_to_dxf(dwg_path)
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    elev_bbox = _find_elevation_bbox(msp)
    if elev_bbox is None:
        return [], None
    ex0, ex1, ey0, ey1 = elev_bbox
    margin = 50.0

    segs = []
    for e in msp:
        if e.dxf.layer != "S-RBAR" or e.dxftype() != "LINE":
            continue
        x0, y0, _ = e.dxf.start
        x1, y1, _ = e.dxf.end
        if min(x0, x1) < ex0 - margin or max(x0, x1) > ex1 + margin:
            continue
        if min(y0, y1) < ey0 - margin or max(y0, y1) > ey1 + margin:
            continue
        if math.hypot(x1 - x0, y1 - y0) < 1e-6:
            continue
        segs.append(Seg(x0, y0, x1, y1, _revit_set_id(e)))

    rails = _merge_rails(segs)
    line_bars = _pair_rails(rails)
    # _merge_collinear_bars (rebar3d's diameter-aware second merge pass) was
    # tried here and measured net-negative on this drawing set specifically
    # (geo_reconcile.py: PW-GF-02 -49%->-57%) - its interval union appears to
    # be deduplicating overlapping candidate-pair detections more aggressively
    # than intended, net-shrinking real coverage rather than only bridging
    # gaps. Left defined but unused rather than deleted, in case a future
    # session wants to debug why (rebar3d's own drawings don't show this
    # effect - a real difference in this set's fragment/overlap pattern, not
    # a copy-paste bug found yet). arc-pairing + chaining ARE kept: they
    # only ever ADD real bent-shape detections (gated to require an actual
    # drawn arc, never fusing two independent straight bars - see
    # chain_bars), so they can't cause this kind of loss.
    arc_bars = _pair_arcs(msp, elev_bbox, margin)
    bars = chain_bars(line_bars + arc_bars)

    # Defensive: the perpendicular midline-correction in _pair_rails can
    # occasionally reconstruct a point that drifts outside the source
    # segments' real span (unresolved edge case in rail matching) -
    # never trust an output bar (any of its vertices) that lands outside
    # the elevation itself.
    m = margin

    def _inside(pt):
        return ex0 - m <= pt[0] <= ex1 + m and ey0 - m <= pt[1] <= ey1 + m

    bars = [b for b in bars if all(_inside(p) for p in b.points)]

    vertical_clusters, horizontal_clusters = _find_section_clusters(msp, elev_bbox)
    if vertical_clusters or horizontal_clusters:
        h_evidence, v_evidence_raw, thickness_mm = _build_z_evidence(msp, vertical_clusters, horizontal_clusters)
        v_evidence = _remap_v_evidence(v_evidence_raw, elev_bbox)
        # Z assignment only makes sense for genuinely straight (2-point)
        # bars - chained bend shapes keep z=0/"none", same honest gap as
        # before rather than guessing a depth for a multi-segment shape.
        straight = [b for b in bars if not b.mid_pts]
        bent = [b for b in bars if b.mid_pts]
        bars = _assign_z(straight, h_evidence, v_evidence, thickness_mm) + bent

    return bars, elev_bbox


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1])
    bars, bbox = extract_bars(p)
    print(f"elevation bbox: {bbox}")
    print(f"{len(bars)} bars reconstructed")
    from collections import Counter
    c = Counter(b.dia_mm for b in bars)
    for d, n in sorted(c.items()):
        print(f"  T{d:.0f}: {n} bars")
