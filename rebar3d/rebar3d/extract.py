"""Extract rebar centerlines from a view.

Bars are drawn as double lines (the true bar outline): two parallel segments
separated by the bar diameter, joined by arcs at bends and hooks. Pairing
parallel segments yields the centerline and the diameter; concentric arc
pairs yield bend centerlines; chaining joins them into full bar shapes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .loader import Ent, arc_points

STD_DIAMETERS = (6, 8, 10, 12, 16, 20, 25, 32)
MIN_DIA, MAX_DIA = 5.0, 34.0


def snap_diameter(d: float, tol: float = 2.0) -> int | None:
    """Nearest standard bar diameter, or None if d isn't actually one.

    Un-gated nearest-snap used to force every stray gap (crossing dimension
    witness lines, mis-paired rails, noise) into a real diameter — including
    ones absent from the drawing's own bar schedule (fabricated T25/T32
    "bars"). A gap has to land within `tol` of a standard size to count.
    """
    best = min(STD_DIAMETERS, key=lambda s: abs(s - d))
    return best if abs(best - d) <= tol else None


@dataclass
class Bar2D:
    """A bar centerline in view coordinates (sequence of 2D points)."""

    points: list[tuple[float, float]]
    diameter: float
    view_role: str = ""  # filled in later (elevation / section)

    @property
    def length(self) -> float:
        return sum(
            math.dist(self.points[i], self.points[i + 1]) for i in range(len(self.points) - 1)
        )


# ---------------------------------------------------------------- segments

@dataclass
class _Seg:
    p0: tuple[float, float]
    p1: tuple[float, float]
    used: bool = False

    def __post_init__(self):
        dx = self.p1[0] - self.p0[0]
        dy = self.p1[1] - self.p0[1]
        self.len = math.hypot(dx, dy)
        # canonical angle in [0, pi); all derived quantities use the
        # canonical direction so parallel/antiparallel segments share a frame
        self.angle = math.atan2(dy, dx) % math.pi if self.len > 0 else 0.0
        self.ux, self.uy = math.cos(self.angle), math.sin(self.angle)
        # normal offset (signed distance of line from origin along normal)
        self.noff = -self.uy * self.p0[0] + self.ux * self.p0[1]
        # parametric range along direction
        t0 = self.p0[0] * self.ux + self.p0[1] * self.uy
        t1 = self.p1[0] * self.ux + self.p1[1] * self.uy
        self.t0, self.t1 = min(t0, t1), max(t0, t1)


def pair_lines(ents: list[Ent], min_len: float = 30.0, seg_min: float = 6.0) -> list[Bar2D]:
    """Pair parallel S-RBAR lines separated by a bar diameter into centerlines."""
    segs: list[_Seg] = []
    for e in ents:
        if e.kind == "LINE":
            s = _Seg(e.points[0], e.points[1])
            if s.len >= seg_min:
                segs.append(s)
        elif e.kind == "LWPOLYLINE":
            pts = e.points + ([e.points[0]] if e.closed else [])
            for i in range(len(pts) - 1):
                s = _Seg(pts[i], pts[i + 1])
                if s.len >= seg_min:
                    segs.append(s)

    # Bar outlines are trimmed where other bars cross, so one side of a bar
    # is many collinear fragments — and hidden runs (inside concrete) are
    # dashed, i.e. many short collinear pieces. Build "rails" first: all
    # segments sharing (angle, normal offset), with fragments and dashes
    # merged across small gaps. Then pair rails separated by a bar diameter.
    rails: dict[tuple[int, int], list[_Seg]] = {}
    for s in segs:
        key = (round(s.angle / 0.005), round(s.noff / 1.5))
        rails.setdefault(key, []).append(s)

    @dataclass
    class _Rail:
        angle: float
        noff: float
        ivs: list[list[float]]  # merged [t0, t1] intervals

    def merge_ivs(ivs: list[tuple[float, float]], gap_tol: float = 60.0) -> list[list[float]]:
        ivs = sorted(ivs)
        out = [list(ivs[0])]
        for t0, t1 in ivs[1:]:
            if t0 <= out[-1][1] + gap_tol:
                out[-1][1] = max(out[-1][1], t1)
            else:
                out.append([t0, t1])
        return out

    rail_list: list[_Rail] = []
    for (ak, nk), group in rails.items():
        angle = sum(s.angle for s in group) / len(group)
        noff = sum(s.noff for s in group) / len(group)
        rail_list.append(_Rail(angle, noff, merge_ivs([(s.t0, s.t1) for s in group])))

    # pair rails: same angle bucket, noff gap = bar diameter
    by_angle: dict[int, list[_Rail]] = {}
    for r in rail_list:
        by_angle.setdefault(round(r.angle / 0.005), []).append(r)

    bars: list[Bar2D] = []
    for group in by_angle.values():
        group.sort(key=lambda r: r.noff)
        used_iv: set[tuple[int, int]] = set()  # (rail idx, iv idx) claims
        # candidate pairings, longest overlap first, each interval used once
        cands = []
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                gap = group[j].noff - group[i].noff
                if gap > MAX_DIA:
                    break
                if gap < MIN_DIA:
                    continue
                for ii, (a0, a1) in enumerate(group[i].ivs):
                    for jj, (b0, b1) in enumerate(group[j].ivs):
                        lo, hi = max(a0, b0), min(a1, b1)
                        if hi - lo >= min_len:
                            cands.append((hi - lo, i, ii, j, jj, lo, hi, gap))
        cands.sort(reverse=True)
        for _, i, ii, j, jj, lo, hi, gap in cands:
            if (i, ii) in used_iv or (j, jj) in used_iv:
                continue
            used_iv.add((i, ii))
            used_iv.add((j, jj))
            r = group[i]
            noff = (r.noff + group[j].noff) / 2
            ux, uy = math.cos(r.angle), math.sin(r.angle)
            p0 = (ux * lo - uy * noff, uy * lo + ux * noff)
            p1 = (ux * hi - uy * noff, uy * hi + ux * noff)
            bars.append(Bar2D([p0, p1], gap))
    return bars


def pair_arcs(ents: list[Ent]) -> list[Bar2D]:
    """Pair concentric arcs (bar bends) into centerline arcs."""
    arcs = [e for e in ents if e.kind == "ARC" and e.radius > 1.0]
    used = [False] * len(arcs)
    bars: list[Bar2D] = []
    for i, a in enumerate(arcs):
        if used[i]:
            continue
        for j in range(i + 1, len(arcs)):
            if used[j]:
                continue
            b = arcs[j]
            if math.dist(a.center, b.center) > 2.0:
                continue
            gap = abs(a.radius - b.radius)
            if not (MIN_DIA <= gap <= MAX_DIA):
                continue
            # angular ranges should roughly agree
            if abs((a.start_angle - b.start_angle) % 360) > 15 and abs((a.start_angle - b.start_angle) % 360) < 345:
                continue
            used[i] = used[j] = True
            mid = Ent(
                "ARC",
                a.layer,
                center=a.center,
                radius=(a.radius + b.radius) / 2,
                start_angle=a.start_angle,
                end_angle=a.end_angle,
            )
            bars.append(Bar2D(arc_points(mid, n=8), gap))
            break
    return bars


# ---------------------------------------------------------------- chaining

def _merge_collinear(bars: list[Bar2D], tol_off: float = 1.5, tol_gap: float = 60.0) -> list[Bar2D]:
    """Merge straight centerlines that are collinear and touching/overlapping."""
    straight = [b for b in bars if len(b.points) == 2]
    other = [b for b in bars if len(b.points) != 2]
    groups: dict[tuple[int, int, int], list[Bar2D]] = {}
    for b in straight:
        s = _Seg(b.points[0], b.points[1])
        key = (round(s.angle / 0.005), round(s.noff / tol_off), round(b.diameter))
        groups.setdefault(key, []).append(b)
    merged: list[Bar2D] = []
    for key, group in groups.items():
        s0 = _Seg(group[0].points[0], group[0].points[1])
        ux, uy = math.cos(s0.angle), math.sin(s0.angle)
        noff = s0.noff
        ivs = []
        for b in group:
            t0 = b.points[0][0] * ux + b.points[0][1] * uy
            t1 = b.points[1][0] * ux + b.points[1][1] * uy
            ivs.append((min(t0, t1), max(t0, t1), b.diameter))
        ivs.sort()
        cur0, cur1, dia = ivs[0]
        dias = [dia]
        out = []
        for t0, t1, d in ivs[1:]:
            if t0 <= cur1 + tol_gap:
                cur1 = max(cur1, t1)
                dias.append(d)
            else:
                out.append((cur0, cur1, sum(dias) / len(dias)))
                cur0, cur1, dias = t0, t1, [d]
        out.append((cur0, cur1, sum(dias) / len(dias)))
        for t0, t1, d in out:
            p0 = (ux * t0 - uy * noff, uy * t0 + ux * noff)
            p1 = (ux * t1 - uy * noff, uy * t1 + ux * noff)
            merged.append(Bar2D([p0, p1], d))
    return merged + other


def chain_bars(bars: list[Bar2D], tol: float = 4.0, tol_dia: float = 3.0) -> list[Bar2D]:
    """Join centerline pieces (lines + bend arcs) whose endpoints coincide.

    Endpoint proximity alone isn't enough: in a dense mesh, unrelated bars
    of *different* diameters routinely terminate at the same corner/edge
    (e.g. a T20 and a T12 both ending at the same opening edge). Fusing
    those blends their diameters into a bogus in-between value — sometimes
    landing on another real standard size — which silently steals length
    from two real bars and fabricates a third. Only chain fragments whose
    diameter is already close to the chain's running average.
    """
    bars = _merge_collinear(bars)
    used = [False] * len(bars)

    def ends(b: Bar2D):
        return b.points[0], b.points[-1]

    chains: list[Bar2D] = []
    for i, b in enumerate(bars):
        if used[i]:
            continue
        used[i] = True
        pts = list(b.points)
        dias = [b.diameter * b.length]
        wlen = [b.length]
        grew = True
        while grew:
            grew = False
            cur_dia = sum(dias) / max(sum(wlen), 1e-9)
            for j, c in enumerate(bars):
                if used[j] or abs(c.diameter - cur_dia) > tol_dia:
                    continue
                c0, c1 = ends(c)
                if math.dist(pts[-1], c0) <= tol:
                    pts += c.points[1:]
                elif math.dist(pts[-1], c1) <= tol:
                    pts += c.points[-2::-1]
                elif math.dist(pts[0], c1) <= tol:
                    pts = c.points[:-1] + pts
                elif math.dist(pts[0], c0) <= tol:
                    pts = c.points[::-1][:-1] + pts
                else:
                    continue
                used[j] = True
                dias.append(c.diameter * c.length)
                wlen.append(c.length)
                grew = True
        dia = sum(dias) / max(sum(wlen), 1e-9)
        chains.append(Bar2D(pts, dia))
    return chains


def extract_bars(view_ents: list[Ent], min_len: float = 30.0) -> list[Bar2D]:
    rbar = [e for e in view_ents if e.layer == "S-RBAR"]
    bars = pair_lines(rbar, min_len=min_len) + pair_arcs(rbar)
    return chain_bars(bars)


# ---------------------------------------------------------------- outline

def wall_outline(view_ents: list[Ent]) -> tuple[tuple[float, float, float, float], list[list[tuple[float, float]]]]:
    """Panel bbox from the outline layer plus any closed loops (openings) inside it."""
    wall = [e for e in view_ents if e.layer == "A-WALL"]
    if not wall:  # slabs use A-FLOR
        wall = [e for e in view_ents if e.layer.startswith("A-FLOR")]
    xs, ys = [], []
    for e in wall:
        x0, y0, x1, y1 = e.bbox
        xs += [x0, x1]
        ys += [y0, y1]
    bbox = (min(xs), min(ys), max(xs), max(ys))

    # closed loops strictly inside the bbox = openings
    loops: list[list[tuple[float, float]]] = []
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    for e in wall:
        if e.kind == "LWPOLYLINE" and e.closed and len(e.points) >= 4:
            x0, y0, x1, y1 = e.bbox
            if (x1 - x0) < 0.95 * w and (y1 - y0) < 0.95 * h:
                loops.append(e.points)
    return bbox, loops
