from __future__ import annotations

from typing import List, Tuple

from core.reconstruction.models import Point3D, PhysicalBar
from core.reconstruction.tube_sweep import sweep_bar_path


class BarTriangulator:
    """
    Sweeps a PhysicalBar's centerline into a single continuous manifold
    tube (see core/reconstruction/tube_sweep.py and
    docs/audits/phase10/10.2_continuous_tube_sweep.md) -- one mesh per bar,
    not one independently-capped cylinder per centerline segment.
    """

    def __init__(self, segments: int = 12):
        self.segments = max(6, segments)

    def triangulate(self, bar: PhysicalBar) -> Tuple[List[Point3D], List[Tuple[int, int, int]]]:
        points = list(bar.centerline.points)
        closed = bar.centerline.closed
        if closed and len(points) > 1 and points[0] == points[-1]:
            # sweep_bar_path bridges the last ring back to the first ring
            # itself for closed=True; a duplicated closing point would
            # produce a degenerate zero-length final segment.
            points = points[:-1]
        return sweep_bar_path(points, bar.radius, closed, segments=self.segments)
