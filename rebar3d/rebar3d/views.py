"""Cluster modelspace entities into separate views (elevation, sections, details)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .loader import Ent

# Layers that carry real geometry (not annotation) — used to seed clustering.
GEOM_LAYERS = ("S-RBAR", "A-WALL", "S-BEAM", "S-SLAB", "A-FLOR", "A-DETL", "A-GENM", "S-COLS")


class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, a: int) -> int:
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


@dataclass
class View:
    ents: list[Ent] = field(default_factory=list)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        boxes = [e.bbox for e in self.ents]
        return (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )

    @property
    def size(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bbox
        return (x1 - x0, y1 - y0)

    def count(self, layer_prefix: str) -> int:
        return sum(1 for e in self.ents if e.layer.startswith(layer_prefix))


def cluster_views(ents: list[Ent], margin: float = 120.0, cell: float = 250.0) -> list[View]:
    """Group geometry entities into views via grid-hash connected components.

    Each entity's bbox is inflated by `margin`; entities whose inflated boxes
    share a grid cell are merged. Views come back sorted by rebar count desc.
    """
    geo = [e for e in ents if e.layer.startswith(GEOM_LAYERS)]
    uf = _UF(len(geo))
    grid: dict[tuple[int, int], int] = {}
    for i, e in enumerate(geo):
        x0, y0, x1, y1 = e.bbox
        x0 -= margin
        y0 -= margin
        x1 += margin
        y1 += margin
        for gx in range(int(x0 // cell), int(x1 // cell) + 1):
            for gy in range(int(y0 // cell), int(y1 // cell) + 1):
                key = (gx, gy)
                if key in grid:
                    uf.union(grid[key], i)
                else:
                    grid[key] = i

    groups: dict[int, View] = {}
    for i, e in enumerate(geo):
        groups.setdefault(uf.find(i), View()).ents.append(e)

    views = sorted(groups.values(), key=lambda v: v.count("S-RBAR"), reverse=True)

    # attach annotation entities (text etc.) to the view whose bbox contains them
    boxes = [v.bbox for v in views]
    for e in ents:
        if e.layer.startswith(GEOM_LAYERS):
            continue
        bx0, by0, bx1, by1 = e.bbox
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        for v, (x0, y0, x1, y1) in zip(views, boxes):
            if x0 - margin <= cx <= x1 + margin and y0 - margin <= cy <= y1 + margin:
                v.ents.append(e)
                break
    return views


def elevation_candidates(views: list[View], min_ratio: float = 0.3,
                         min_dim: float = 300.0) -> list[View]:
    """Views that look like a full member elevation in their own right, not a
    section/detail cut of another one.

    A sheet occasionally carries more than one distinct member (e.g. two
    different precast column marks side by side) — each with its own dense
    double-line rebar and its own outline layer, at a scale comparable to
    the sheet's largest view. `views[0]` alone would only reconstruct one
    of them and silently drop the other's bars entirely.

    Rebar density alone (`min_ratio` of the largest view's count) isn't
    enough to tell a sibling member from a section/edge-band cut of the
    *same* member — a section can carry plenty of double-line mesh too.
    What a section can't have is plausible member proportions: it's drawn
    collapsed to wall-thickness scale (~150-250mm) along its cut axis,
    while a real member's own cross-section runs `min_dim` or wider in
    *both* directions.
    """
    from .extract import wall_outline

    if not views:
        return []
    floor = min_ratio * views[0].count("S-RBAR")
    out = []
    for v in views:
        if v.count("S-RBAR") < floor:
            continue
        if not (v.count("A-WALL") > 0 or v.count("S-COLS") > 0 or v.count("A-FLOR") > 0):
            continue
        bbox, _ = wall_outline(v.ents)
        if min(bbox[2] - bbox[0], bbox[3] - bbox[1]) < min_dim:
            continue
        out.append(v)
    return out
