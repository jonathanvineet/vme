"""
viewer/renderer/node_renderer.py

NodeRenderer — renders CanonicalNodes as point cloud in the shared scene.
Colour is mapped to node degree: Red=1, Green=2, Blue=3+
"""
from __future__ import annotations

import numpy as np
import pyvista as pv

from viewer.renderer.base_renderer import BaseRenderer
from viewer.scene import SceneManager


class NodeRenderer(BaseRenderer):
    LAYER_NAME = SceneManager.LAYER_NODES

    def build(self):
        repo = self.scene.node_repo
        if not repo or not repo.nodes:
            return

        points, colors = [], []
        for node in repo.nodes.values():
            pos = node.position
            x, y = pos[0], pos[1]
            z = pos[2] if len(pos) > 2 else 0.0
            points.append([x, y, z])
            deg = node.incident_edges
            if deg == 1:
                colors.append([220, 50, 50])      # red — terminal
            elif deg == 2:
                colors.append([50, 200, 50])      # green — chain
            else:
                colors.append([50, 100, 230])     # blue — junction

        mesh = pv.PolyData(np.array(points, dtype=float))
        mesh.point_data["colors"] = np.array(colors, dtype=np.uint8)

        a = self.plotter.add_mesh(
            mesh,
            scalars="colors",
            rgb=True,
            point_size=4,
            render_points_as_spheres=True,
            name="nodes",
            pickable=True,
        )
        self._add_actor(a)
