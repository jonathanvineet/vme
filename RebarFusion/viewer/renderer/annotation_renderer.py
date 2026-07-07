from viewer.renderer.base import BaseRenderer
from viewer.scene import SceneManager
import numpy as np

class AnnotationRenderer(BaseRenderer):
    LAYER_NAME = SceneManager.LAYER_ANNOTATIONS

    def build(self):
        canon_repo = self.scene.canon_repo
        if not canon_repo:
            return

        import pyvista as pv
        
        # Dimensions are grey
        for d in canon_repo.dimensions:
            points = np.array([d.p1, d.p2], dtype=float)
            mesh = pv.PolyData(points)
            mesh.lines = np.array([2, 0, 1])
            name = f"anno_dim_{str(d.id)[:8]}"
            actor = self.plotter.add_mesh(mesh, color=(0.6, 0.6, 0.6), line_width=1.0, name=name)
            self._add_actor(actor)

class AssociationRenderer(BaseRenderer):
    # For now, put this on the engineering layer, or a custom one
    LAYER_NAME = SceneManager.LAYER_MODEL
    
    def build(self):
        # Placeholder for drawing associations if we persist them in scene
        pass
