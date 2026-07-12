"""
Phase 10E — Continuous Tube Sweep.

Replaces the per-segment independently-capped-cylinder approach in
core/reconstruction/triangulator.py (documented as a latent, then actively
exercised, defect in docs/audits/phase10/10.0 and 10.1) with a single
continuous manifold tube per bar, built from parallel transport frames
propagated along the whole path. Design: docs/audits/phase10/10.2_continuous_tube_sweep.md.

Frenet frames are deliberately not used: they are undefined/unstable
wherever curvature is near zero, which is the majority case for this
project's geometry (most recovered paths are one LINE plus a short ARC).
Parallel transport frames carry straight through unchanged on straight
runs and only rotate where the tangent actually changes, matching how a
real swept solid behaves.
"""

from __future__ import annotations

import math
from typing import List, Tuple

Point3D = Tuple[float, float, float]
Vector3D = Tuple[float, float, float]


def _sub(a: Point3D, b: Point3D) -> Vector3D:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vector3D, b: Vector3D) -> Vector3D:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Vector3D, s: float) -> Vector3D:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Vector3D, b: Vector3D) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vector3D, b: Vector3D) -> Vector3D:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vector3D) -> float:
    return math.sqrt(_dot(a, a))


def _normalize(a: Vector3D) -> Vector3D:
    n = _norm(a)
    if n <= 1e-12:
        return (1.0, 0.0, 0.0)
    return _scale(a, 1.0 / n)


def _tangents(points: List[Point3D], closed: bool) -> List[Vector3D]:
    n = len(points)
    tangents: List[Vector3D] = []
    for i in range(n):
        if closed:
            prev_p = points[i - 1]
            next_p = points[(i + 1) % n]
            t = _normalize(_sub(next_p, prev_p))
        elif i == 0:
            t = _normalize(_sub(points[1], points[0])) if n > 1 else (1.0, 0.0, 0.0)
        elif i == n - 1:
            t = _normalize(_sub(points[i], points[i - 1]))
        else:
            t = _normalize(_sub(points[i + 1], points[i - 1]))
        # Degenerate (zero-length neighbor segment): reuse previous tangent
        # rather than emit a meaningless direction.
        if _norm(t) <= 1e-9 and tangents:
            t = tangents[-1]
        tangents.append(t)
    return tangents


def _seed_frame(tangent: Vector3D) -> Tuple[Vector3D, Vector3D]:
    ref = (0.0, 0.0, 1.0)
    if abs(_dot(tangent, ref)) > 0.95:
        ref = (1.0, 0.0, 0.0)
    normal = _normalize(_cross(ref, tangent))
    binormal = _cross(tangent, normal)
    return normal, binormal


def _rotate(v: Vector3D, axis: Vector3D, angle: float) -> Vector3D:
    """Rodrigues' rotation formula."""
    if abs(angle) <= 1e-12:
        return v
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    term1 = _scale(v, cos_a)
    term2 = _scale(_cross(axis, v), sin_a)
    term3 = _scale(axis, _dot(axis, v) * (1.0 - cos_a))
    return _add(_add(term1, term2), term3)


def _parallel_transport_frames(tangents: List[Vector3D]) -> List[Tuple[Vector3D, Vector3D]]:
    """One (normal, binormal) pair per tangent, propagated with minimal
    rotation frame-to-frame so straight runs carry the frame through
    unchanged instead of twisting (the Frenet-frame failure mode)."""
    frames: List[Tuple[Vector3D, Vector3D]] = []
    normal, binormal = _seed_frame(tangents[0])
    frames.append((normal, binormal))
    for i in range(1, len(tangents)):
        t_prev, t_curr = tangents[i - 1], tangents[i]
        cos_angle = max(-1.0, min(1.0, _dot(t_prev, t_curr)))
        angle = math.acos(cos_angle)
        if angle <= 1e-9:
            frames.append(frames[-1])
            continue
        axis = _normalize(_cross(t_prev, t_curr))
        normal = _normalize(_rotate(frames[-1][0], axis, angle))
        binormal = _cross(t_curr, normal)
        frames.append((normal, binormal))
    return frames


def sweep_bar_path(points: List[Point3D], radius: float, closed: bool,
                    segments: int = 12) -> Tuple[List[Point3D], List[Tuple[int, int, int]]]:
    """
    Stages 2-7 of the continuous tube sweep. Returns (vertices, faces) for
    ONE continuous manifold tube along the whole path -- unlike the old
    per-segment approach, interior joints get no caps at all, just a
    shared ring bridged on both sides.
    """
    n = len(points)
    if n < 2 or radius <= 0:
        return [], []

    tangents = _tangents(points, closed)
    frames = _parallel_transport_frames(tangents)

    vertices: List[Point3D] = []
    ring_start_indices: List[int] = []
    for i, (p, (normal, binormal)) in enumerate(zip(points, frames)):
        ring_start_indices.append(len(vertices))
        for s in range(segments):
            theta = (2.0 * math.pi * s) / segments
            offset = _add(_scale(normal, radius * math.cos(theta)), _scale(binormal, radius * math.sin(theta)))
            vertices.append(_add(p, offset))

    faces: List[Tuple[int, int, int]] = []
    ring_pairs = list(zip(range(n), range(1, n))) if not closed else list(zip(range(n), [(i + 1) % n for i in range(n)]))
    for i, j in ring_pairs:
        base_i, base_j = ring_start_indices[i], ring_start_indices[j]
        for s in range(segments):
            s_next = (s + 1) % segments
            a, b = base_i + s, base_i + s_next
            c, d = base_j + s, base_j + s_next
            faces.append((a, c, b))
            faces.append((b, c, d))

    if not closed:
        start_center = len(vertices)
        vertices.append(points[0])
        base0 = ring_start_indices[0]
        for s in range(segments):
            s_next = (s + 1) % segments
            faces.append((start_center, base0 + s_next, base0 + s))

        end_center = len(vertices)
        vertices.append(points[-1])
        base_last = ring_start_indices[-1]
        for s in range(segments):
            s_next = (s + 1) % segments
            faces.append((end_center, base_last + s, base_last + s_next))

    return vertices, faces
