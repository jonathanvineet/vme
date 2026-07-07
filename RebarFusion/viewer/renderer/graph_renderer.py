"""
viewer/renderer/graph_renderer.py

GraphRenderer — renders connectivity graph edges as lines in the shared scene.
"""
from __future__ import annotations

import numpy as np
import pyvista as pv

from viewer.renderer.base_renderer import BaseRenderer
from viewer.scene import SceneManager


class GraphRenderer(BaseRenderer):
    LAYER_NAME = SceneManager.LAYER_GRAPH

    def build(self):
        g = self.scene.graph
        if not g or not g.edges:
            return

        points, cells = [], []
        idx = 0
        for edge in g.edges.values():
            n1 = g.nodes.get(edge.start_node_uuid)
            n2 = g.nodes.get(edge.end_node_uuid)
            if n1 is None or n2 is None:
                continue
            p1 = list(n1.position) + ([0.0] if len(n1.position) < 3 else [])
            p2 = list(n2.position) + ([0.0] if len(n2.position) < 3 else [])
            points.extend([p1[:3], p2[:3]])
            cells.extend([2, idx, idx + 1])
            idx += 2

        if not points:
            return

        mesh = pv.PolyData()
        mesh.points = np.array(points, dtype=float)
        mesh.lines = np.array(cells)
        a = self.plotter.add_mesh(mesh, color=(0.6, 0.9, 0.6), line_width=1.0,
                                  opacity=0.6, name="graph_edges", pickable=False)
        self._add_actor(a)
