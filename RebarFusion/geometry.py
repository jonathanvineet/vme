"""Geometry helpers for rebar extraction"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import math
from shapely.geometry import LineString, Point, box
from shapely.ops import linemerge, unary_union


def line_length(line: LineString) -> float:
    return float(line.length)


def line_angle_deg(line: LineString) -> float:
    x0, y0 = line.coords[0]
    x1, y1 = line.coords[-1]
    ang = math.degrees(math.atan2((y1 - y0), (x1 - x0)))
    # normalize to 0-180
    ang = ang % 180.0
    return ang


def center_point(line: LineString) -> Tuple[float, float]:
    mid = line.interpolate(0.5, normalized=True)
    return (float(mid.x), float(mid.y))


def bounding_box(line: LineString) -> Tuple[float, float, float, float]:
    minx, miny, maxx, maxy = line.bounds
    return (float(minx), float(miny), float(maxx), float(maxy))


def merge_segments(segments: List[LineString], tolerance: float = 1.0) -> List[LineString]:
    """Merge many small segments into continuous LineStrings.

    Uses unary_union + linemerge to combine segments, then returns
    a list of LineString objects approximating merged rebars.
    """
    if not segments:
        return []
    # make union
    u = unary_union(segments)
    merged = linemerge(u)
    result = []
    if isinstance(merged, LineString):
        result = [merged]
    else:
        # MultiLineString
        result = [ls for ls in merged]
    # optionally simplify small dangles by buffering
    return result
