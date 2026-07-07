from __future__ import annotations

import math
from typing import List, Tuple

from core.reconstruction.models import Point3D, PhysicalBar


class BarTriangulator:
    def __init__(self, segments: int = 12):
        self.segments = max(6, segments)

    def triangulate(self, bar: PhysicalBar) -> Tuple[List[Point3D], List[Tuple[int, int, int]]]:
        vertices: List[Point3D] = []
        faces: List[Tuple[int, int, int]] = []
        points = list(bar.centerline.points)
        if bar.centerline.closed and points and points[0] != points[-1]:
            points.append(points[0])

        for start, end in zip(points, points[1:]):
            base = len(vertices)
            segment_vertices, segment_faces = self._cylinder_segment(start, end, bar.radius)
            vertices.extend(segment_vertices)
            faces.extend((a + base, b + base, c + base) for a, b, c in segment_faces)
        return vertices, faces

    def _cylinder_segment(self, start, end, radius: float):
        sx, sy, sz = start
        ex, ey, ez = end
        dx, dy, dz = ex - sx, ey - sy, ez - sz
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length <= 0:
            return [], []

        ux, uy, uz = dx / length, dy / length, dz / length
        ref = (0.0, 0.0, 1.0)
        if abs(uz) > 0.95:
            ref = (1.0, 0.0, 0.0)

        vx, vy, vz = self._normalize(self._cross((ux, uy, uz), ref))
        wx, wy, wz = self._cross((ux, uy, uz), (vx, vy, vz))

        vertices = []
        for center in (start, end):
            cx, cy, cz = center
            for i in range(self.segments):
                theta = (2.0 * math.pi * i) / self.segments
                rx = math.cos(theta) * vx * radius + math.sin(theta) * wx * radius
                ry = math.cos(theta) * vy * radius + math.sin(theta) * wy * radius
                rz = math.cos(theta) * vz * radius + math.sin(theta) * wz * radius
                vertices.append((cx + rx, cy + ry, cz + rz))

        faces = []
        for i in range(self.segments):
            j = (i + 1) % self.segments
            a = i
            b = j
            c = self.segments + i
            d = self.segments + j
            faces.append((a, c, b))
            faces.append((b, c, d))

        start_center = len(vertices)
        end_center = start_center + 1
        vertices.append(start)
        vertices.append(end)
        for i in range(self.segments):
            j = (i + 1) % self.segments
            faces.append((start_center, j, i))
            faces.append((end_center, self.segments + i, self.segments + j))

        return vertices, faces

    @staticmethod
    def _cross(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    @staticmethod
    def _normalize(v):
        length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        if length <= 0:
            return (1.0, 0.0, 0.0)
        return (v[0] / length, v[1] / length, v[2] / length)
