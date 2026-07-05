from dataclasses import dataclass
from math import atan2, degrees, hypot
from typing import List, Optional, Tuple

# -------------------------------


@dataclass
class Segment:

    start: Tuple[float, float]
    end: Tuple[float, float]
    layer: str


# -------------------------------


@dataclass
class Rebar:

    id: int

    segments: List[Segment]

    start: Tuple[float, float]

    end: Tuple[float, float]

    center: Tuple[float, float]

    length: float

    angle: float

    orientation: str

    bbox: Tuple[float, float, float, float]

    spacing: Optional[float] = None


# -------------------------------


class RebarDetector:

    def __init__(self):

        self.point_tol = 0.5

        self.angle_tol = 5.0

        self.min_length = 50.0

        self.rebar_layers = {

            "S-RBAR",

            "RBAR",

            "REBAR"

        }

        # distance threshold when grouping near segments (drawing units)
        self.group_dist = 75.0

    # -----------------------------------------------------

    def detect(self, entities: List) -> List[Rebar]:

        candidates = self.extract_segments(entities)

        print("Candidate segments:", len(candidates))

        candidates = self.remove_small_segments(candidates)

        print("After filtering:", len(candidates))

        groups = self.group_parallel_segments(candidates)

        print("Groups:", len(groups))

        rebars: List[Rebar] = []

        for i, g in enumerate(groups):

            rebars.append(self.make_rebar(i + 1, g))

        return rebars

    # -----------------------------------------------------

    def extract_segments(self, entities: List) -> List[Segment]:

        segments: List[Segment] = []

        for e in entities:

            layer_name = (e.layer or "").upper()

            if e.entity_type == "LINE":

                if layer_name not in self.rebar_layers:
                    continue

                segments.append(Segment(e.start, e.end, e.layer))

            elif e.entity_type in [

                "POLYLINE",

                "LWPOLYLINE"

            ]:

                if layer_name not in self.rebar_layers:
                    continue

                pts = e.points or []

                for i in range(len(pts) - 1):

                    segments.append(Segment(pts[i], pts[i + 1], e.layer))

        return segments

    # -----------------------------------------------------

    def remove_small_segments(self, segments: List[Segment]) -> List[Segment]:

        out: List[Segment] = []

        for s in segments:

            L = self.distance(s.start, s.end)

            if L >= self.min_length:

                out.append(s)

        return out

    # -----------------------------------------------------

    def group_parallel_segments(self, segments: List[Segment]) -> List[List[Segment]]:

        if not segments:
            return []

        # compute angle for each segment (0-180)
        indexed = []
        for s in segments:
            dx = s.end[0] - s.start[0]
            dy = s.end[1] - s.start[1]
            ang = degrees(atan2(dy, dx)) % 180.0
            indexed.append((s, ang))

        # bin by angle within angle_tol
        bins = {}
        for s, ang in indexed:
            key = round(ang / self.angle_tol) * self.angle_tol
            bins.setdefault(key, []).append((s, ang))

        groups: List[List[Segment]] = []

        # for each angle bin, spatially group by proximity
        for key, items in bins.items():
            unassigned = [it[0] for it in items]
            while unassigned:
                seed = unassigned.pop(0)
                group = [seed]
                i = 0
                while i < len(unassigned):
                    cand = unassigned[i]
                    if self._near_group(seed, cand):
                        group.append(cand)
                        unassigned.pop(i)
                        # do not increment i
                    else:
                        i += 1
                groups.append(group)

        return groups

    # -----------------------------------------------------

    def _near_group(self, a: Segment, b: Segment) -> bool:
        # approximate by min endpoint distance
        d = min(
            self.distance(a.start, b.start),
            self.distance(a.start, b.end),
            self.distance(a.end, b.start),
            self.distance(a.end, b.end),
        )
        return d <= self.group_dist

    # -----------------------------------------------------

    def make_rebar(self, rid: int, segments: List[Segment]) -> Rebar:

        xs = []
        ys = []
        total = 0.0
        angle_sum = 0.0
        angle_weight = 0.0

        for s in segments:
            xs.extend([s.start[0], s.end[0]])
            ys.extend([s.start[1], s.end[1]])
            L = self.distance(s.start, s.end)
            total += L
            ang = degrees(atan2(s.end[1] - s.start[1], s.end[0] - s.start[0]))
            angle_sum += ang * L
            angle_weight += L

        xmin = min(xs)
        xmax = max(xs)
        ymin = min(ys)
        ymax = max(ys)

        bbox = (xmin, ymin, xmax, ymax)

        start = (xmin, ymin)
        end = (xmax, ymax)

        center = ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0)

        angle = (angle_sum / angle_weight) if angle_weight > 0 else 0.0

        length = round(total, 2)

        a = abs(angle)
        if abs(a) < 15:
            orient = "Horizontal"
        elif abs(a) > 75:
            orient = "Vertical"
        else:
            orient = "Diagonal"

        return Rebar(
            id=rid,
            segments=segments,
            start=start,
            end=end,
            center=center,
            length=length,
            angle=round(angle, 2),
            orientation=orient,
            bbox=bbox,
        )

    # -----------------------------------------------------

    def distance(self, a: Tuple[float, float], b: Tuple[float, float]) -> float:

        return hypot(a[0] - b[0], a[1] - b[1])
"""
===========================================================
rebar_detector.py

Detects rebars from CAD entities.

Steps

1. Filter rebar geometry
2. Merge connected segments
3. Compute properties
4. Return Rebar objects

===========================================================
"""

from dataclasses import dataclass
from math import atan2, degrees, hypot
from typing import Optional


# ---------------------------------------------------------
# Rebar Object
# ---------------------------------------------------------

@dataclass
class Rebar:

    id: int

    segments: list

    start: tuple

    end: tuple

    center: tuple

    length: float

    angle: float

    bbox: tuple

    orientation: str

    spacing: Optional[float] = None


# ---------------------------------------------------------
# Detector
# ---------------------------------------------------------

class RebarDetector:

    def __init__(self):

        self.tolerance = 1.0

    # -----------------------------------------------------

    def detect(self, entities):

        # Keep only geometry

        geometry = []

        for e in entities:

            if e.entity_type in [

                "LINE",
                "POLYLINE",
                "LWPOLYLINE"

            ]:

                # Ignore obvious annotation layers

                if "TEXT" in e.layer.upper():
                    continue

                if "DIM" in e.layer.upper():
                    continue

                geometry.append(e)

        # Convert every entity to line segments

        segments = []

        for g in geometry:

            if g.entity_type == "LINE":

                segments.append(

                    {

                        "start": g.start,
                        "end": g.end

                    }

                )

            else:

                pts = g.points

                for i in range(len(pts) - 1):

                    segments.append(

                        {

                            "start": pts[i],
                            "end": pts[i + 1]

                        }

                    )

        # Merge connected segments

        groups = self.merge_segments(segments)

        rebars = []

        rid = 1

        for g in groups:

            rb = self.compute_rebar(rid, g)

            rebars.append(rb)

            rid += 1

        return rebars

    # -----------------------------------------------------

    def merge_segments(self, segments):

        visited = set()

        groups = []

        for i in range(len(segments)):

            if i in visited:
                continue

            stack = [i]

            group = []

            while stack:

                idx = stack.pop()

                if idx in visited:
                    continue

                visited.add(idx)

                group.append(segments[idx])

                for j in range(len(segments)):

                    if j in visited:
                        continue

                    if self.connected(

                        segments[idx],

                        segments[j]

                    ):

                        stack.append(j)

            groups.append(group)

        return groups

    # -----------------------------------------------------

    def connected(self, a, b):

        pts1 = [

            a["start"],
            a["end"]

        ]

        pts2 = [

            b["start"],
            b["end"]

        ]

        for p1 in pts1:

            for p2 in pts2:

                if self.distance(p1, p2) < self.tolerance:

                    return True

        return False

    # -----------------------------------------------------

    def compute_rebar(self, rid, group):

        xs = []
        ys = []

        total = 0

        for s in group:

            xs.append(s["start"][0])
            xs.append(s["end"][0])

            ys.append(s["start"][1])
            ys.append(s["end"][1])

            total += self.distance(

                s["start"],
                s["end"]

            )

        xmin = min(xs)
        xmax = max(xs)

        ymin = min(ys)
        ymax = max(ys)

        bbox = (

            xmin,
            ymin,
            xmax,
            ymax

        )

        start = (

            xmin,
            ymin

        )

        end = (

            xmax,
            ymax

        )

        center = (

            (xmin + xmax) / 2,

            (ymin + ymax) / 2

        )

        angle = degrees(

            atan2(

                end[1] - start[1],

                end[0] - start[0]

            )

        )

        if abs(angle) < 15:

            orient = "Horizontal"

        elif abs(angle) > 75:

            orient = "Vertical"

        else:

            orient = "Diagonal"

        return Rebar(

            id=rid,

            segments=group,

            start=start,

            end=end,

            center=center,

            length=round(total, 2),

            angle=round(angle, 2),

            bbox=bbox,

            orientation=orient

        )

    # -----------------------------------------------------

    def distance(self, a, b):

        return hypot(

            a[0] - b[0],

            a[1] - b[1]

        )