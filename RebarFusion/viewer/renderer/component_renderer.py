"""
viewer/renderer/component_renderer.py

ComponentRenderer — renders connected components as colored wireframes.
Each component gets a deterministic HSV color based on its UUID.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pyvista as pv

from viewer.renderer.base_renderer import BaseRenderer
from viewer.scene import SceneManager


def _uuid_to_rgb(comp_id) -> tuple:
    """Deterministic but visually distinct colour derived from UUID bytes."""
    h = int(hashlib.md5(str(comp_id).encode()).hexdigest()[:6], 16) / 0xFFFFFF
    # Convert hue to RGB (HSV with S=0.8, V=0.9)
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h, 0.80, 0.90)
    return (r, g, b)


class ComponentRenderer(BaseRenderer):
    LAYER_NAME = SceneManager.LAYER_COMPONENTS

    def build(self):
        g = self.scene.graph
        comp_repo = self.scene.comp_repo
        if not g or not comp_repo or not comp_repo.components:
            return

        for comp in comp_repo.components.values():
            color = _uuid_to_rgb(comp.id)
            points, cells = [], []
            idx = 0
            for e_id in comp.edge_ids:
                edge = g.edges.get(e_id)
                if not edge:
                    continue
                n1 = g.nodes.get(edge.start_node_uuid)
                n2 = g.nodes.get(edge.end_node_uuid)
                if n1 is None or n2 is None:
                    continue
                p1 = list(n1.position[:2]) + [0.0]
                p2 = list(n2.position[:2]) + [0.0]
                points.extend([p1, p2])
                cells.extend([2, idx, idx + 1])
                idx += 2

            if not points:
                continue
            mesh = pv.PolyData()
            mesh.points = np.array(points, dtype=float)
            mesh.lines = np.array(cells)
            name = f"comp_{str(comp.id)[:8]}"
            a = self.plotter.add_mesh(mesh, color=color, line_width=1.5,
                                      opacity=0.85, name=name)
            self._add_actor(a)
