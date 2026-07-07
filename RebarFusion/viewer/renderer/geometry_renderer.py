"""
viewer/renderer/geometry_renderer.py

GeometryRenderer — renders Lines, Arcs, Polylines, Circles from the
CanonicalGeometryRepository into the shared PyVista scene.

This is Renderer #1. It is the only renderer that touches raw geometry.
All subsequent renderers work on Nodes, Graph edges, Components, etc.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
import pyvista as pv

from viewer.renderer.base_renderer import BaseRenderer
from viewer.scene import SceneManager

if TYPE_CHECKING:
    pass

# Colour palette ─────────────────────────────────────────────────────────────
COLOUR_LINE     = (0.55, 0.78, 1.0)
COLOUR_ARC      = (1.0,  0.73, 0.25)
COLOUR_POLY     = (0.65, 1.0,  0.65)
COLOUR_CIRCLE   = (1.0,  0.55, 0.55)
COLOUR_SELECTED = (1.0,  1.0,  0.0)


class GeometryRenderer(BaseRenderer):
    LAYER_NAME = SceneManager.LAYER_GEOMETRY

    # ─── Build ────────────────────────────────────────────────────────────────

    def build(self):
        repo = self.scene.canon_repo
        if repo is None:
            return

        # ── Lines ─────────────────────────────────────────────────────────
        if repo.lines:
            points, cells = [], []
            idx = 0
            for line in repo.lines:
                s, e = np.array(line.start, dtype=float), np.array(line.end, dtype=float)
                if len(s) < 3: s = np.append(s, 0.0)
                if len(e) < 3: e = np.append(e, 0.0)
                points.extend([s, e])
                cells.extend([2, idx, idx + 1])
                idx += 2
            mesh = pv.PolyData()
            mesh.points = np.array(points, dtype=float)
            mesh.lines = np.array(cells)
            a = self.plotter.add_mesh(mesh, color=COLOUR_LINE, line_width=1.0,
                                      name="geo_lines", pickable=True)
            self._add_actor(a)

        # ── Arcs ──────────────────────────────────────────────────────────
        if repo.arcs:
            points, cells = [], []
            idx = 0
            for arc in repo.arcs:
                cx, cy = arc.center[0], arc.center[1]
                r = arc.radius
                sa, ea = arc.start_angle, arc.end_angle
                # Normalise sweep
                if ea < sa:
                    ea += 360.0
                n_pts = max(16, int(abs(ea - sa) / 5))
                angles = np.linspace(math.radians(sa), math.radians(ea), n_pts)
                pts = [(cx + r * math.cos(a), cy + r * math.sin(a), 0.0) for a in angles]
                seg_start = idx
                for pt in pts:
                    points.append(pt)
                for i in range(len(pts) - 1):
                    cells.extend([2, idx + i, idx + i + 1])
                idx += len(pts)
            mesh = pv.PolyData()
            mesh.points = np.array(points, dtype=float)
            mesh.lines = np.array(cells)
            a = self.plotter.add_mesh(mesh, color=COLOUR_ARC, line_width=1.0, name="geo_arcs")
            self._add_actor(a)

        # ── Polylines ─────────────────────────────────────────────────────
        if repo.polylines:
            points, cells = [], []
            idx = 0
            for poly in repo.polylines:
                verts = [np.array(v, dtype=float) for v in poly.vertices]
                verts = [np.append(v, 0.0) if len(v) < 3 else v for v in verts]
                seg_start = idx
                for v in verts:
                    points.append(v)
                for i in range(len(verts) - 1):
                    cells.extend([2, idx + i, idx + i + 1])
                idx += len(verts)
            mesh = pv.PolyData()
            mesh.points = np.array(points, dtype=float)
            mesh.lines = np.array(cells)
            a = self.plotter.add_mesh(mesh, color=COLOUR_POLY, line_width=1.0, name="geo_polylines")
            self._add_actor(a)

        # ── Circles ───────────────────────────────────────────────────────
        if repo.circles:
            points, cells = [], []
            idx = 0
            n_pts = 32
            for circle in repo.circles:
                cx, cy = circle.center[0], circle.center[1]
                r = circle.radius
                angles = np.linspace(0, 2 * math.pi, n_pts, endpoint=False)
                pts = [(cx + r * math.cos(a), cy + r * math.sin(a), 0.0) for a in angles]
                for pt in pts:
                    points.append(pt)
                for i in range(n_pts):
                    cells.extend([2, idx + i, idx + (i + 1) % n_pts])
                idx += n_pts
            mesh = pv.PolyData()
            mesh.points = np.array(points, dtype=float)
            mesh.lines = np.array(cells)
            a = self.plotter.add_mesh(mesh, color=COLOUR_CIRCLE, line_width=1.0, name="geo_circles")
            self._add_actor(a)
