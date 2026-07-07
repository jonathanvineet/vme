"""
viewer/renderer/recognition_renderer.py  [STUB]

RecognitionRenderer — will colour components by recognized bar type.

Colour scheme (Phase 7+):
  straight_bar      → Blue
  l_bar             → Cyan
  u_bar             → Green
  stirrup           → Yellow
  structural_outline → Orange
  dimension         → Grey
  branch            → Magenta
  leader            → Pink
  unknown           → White

This renderer is intentionally empty until Phase 7 is frozen.
"""
from viewer.renderer.base_renderer import BaseRenderer
from viewer.scene import SceneManager


class RecognitionRenderer(BaseRenderer):
    LAYER_NAME = SceneManager.LAYER_RECOGNITION

    def build(self):
        g = self.scene.graph
        comp_repo = self.scene.comp_repo
        cache = self.scene.recognition_cache
        
        if not g or not comp_repo or not comp_repo.components or not cache:
            return

        COLORS = {
            'straight_bar': (0.3, 0.6, 1.0),     # Blue
            'l_bar': (0.0, 1.0, 1.0),            # Cyan
            'u_bar': (0.3, 1.0, 0.3),            # Green
            'stirrup': (1.0, 1.0, 0.0),          # Yellow
            'structural_outline': (1.0, 0.6, 0.0), # Orange
            'dimension': (0.6, 0.6, 0.6),        # Grey
            'branch': (1.0, 0.0, 1.0),           # Magenta
            'leader': (1.0, 0.4, 0.7),           # Pink
            'unknown': (1.0, 1.0, 1.0)           # White
        }

        import numpy as np
        import pyvista as pv

        for comp in comp_repo.components.values():
            result = cache.get(comp.id)
            label = result.label if result else 'unknown'
            color = COLORS.get(label, (1.0, 1.0, 1.0))
            
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
            name = f"recog_{str(comp.id)[:8]}_{label}"
            a = self.plotter.add_mesh(mesh, color=color, line_width=2.0,
                                      opacity=0.9, name=name)
            self._add_actor(a)
