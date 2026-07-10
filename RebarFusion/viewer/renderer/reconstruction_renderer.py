from __future__ import annotations

import numpy as np
import pyvista as pv

from viewer.renderer.base_renderer import BaseRenderer
from viewer.scene import SceneManager


class BarRenderer(BaseRenderer):
    LAYER_NAME = SceneManager.LAYER_BARS

    def build(self):
        bars = getattr(self.scene, "physical_bars", None) or []
        for bar in bars:
            if len(bar.path) < 2:
                continue
            points = np.array(bar.path, dtype=float)
            lines = []
            for idx in range(len(points) - 1):
                lines.extend([2, idx, idx + 1])
            mesh = pv.PolyData()
            mesh.points = points
            mesh.lines = np.array(lines)
            selected = bar.uuid == self.scene.selected_bar_uuid
            actor = self.plotter.add_mesh(
                mesh,
                color=(1.0, 0.92, 0.35) if selected else (0.95, 0.72, 0.25),
                line_width=max(3.0, bar.diameter / 2.5) if selected else max(2.0, bar.diameter / 3.0),
                opacity=1.0 if selected else 0.95,
                name=f"physical_bar_{str(bar.uuid)[:8]}",
            )
            self._add_actor(actor)


class MeshRenderer(BaseRenderer):
    LAYER_NAME = SceneManager.LAYER_MESHES

    def build(self):
        meshes = getattr(self.scene, "reconstruction_meshes", None) or []
        for mesh in meshes:
            if not mesh.vertices or not mesh.faces:
                continue
            cells = []
            for face in mesh.faces:
                cells.extend([3, *face])
            poly = pv.PolyData()
            poly.points = np.array(mesh.vertices, dtype=float)
            poly.faces = np.array(cells)
            selected = mesh.uuid == self.scene.selected_mesh_uuid
            actor = self.plotter.add_mesh(
                poly,
                color=(0.95, 0.95, 1.0) if selected else (0.78, 0.78, 0.82),
                opacity=1.0 if selected else 0.92,
                smooth_shading=True,
                name=f"reconstruction_mesh_{str(mesh.uuid)[:8]}",
            )
            self._add_actor(actor)
