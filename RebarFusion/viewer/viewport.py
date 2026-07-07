"""
viewer/viewport.py

PyVista-backed 3D/2D viewport widget embedded in the Qt application.
Manages the renderer plugin registry. Renderers self-register here.
"""
from __future__ import annotations

from typing import List

import pyvista as pv
from pyvistaqt import QtInteractor

from viewer.scene import SceneManager
from viewer.renderer.base_renderer import BaseRenderer
from viewer.renderer.geometry_renderer import GeometryRenderer
from viewer.renderer.node_renderer import NodeRenderer
from viewer.renderer.graph_renderer import GraphRenderer
from viewer.renderer.component_renderer import ComponentRenderer
from viewer.renderer.recognition_renderer import RecognitionRenderer


class ViewportWidget(QtInteractor):
    """
    Extends QtInteractor with a renderer plugin registry.

    Usage
    -----
    viewport = ViewportWidget(scene, parent)
    # Renderers are constructed and registered automatically.
    # External code can call viewport.add_renderer(MyRenderer) to extend.
    """

    def __init__(self, scene: SceneManager, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._renderers: List[BaseRenderer] = []

        # Dark background
        self.set_background("#0d0d1a")

        # Register built-in renderers in display priority order
        self.add_renderer(GeometryRenderer(scene, self))
        self.add_renderer(NodeRenderer(scene, self))
        self.add_renderer(GraphRenderer(scene, self))
        self.add_renderer(ComponentRenderer(scene, self))
        self.add_renderer(RecognitionRenderer(scene, self))  # stub

        # Camera: top-down 2D view by default
        self.view_xy()
        self.enable_parallel_projection()

        # Camera preset actions exposed for toolbar
        self.camera_presets = {
            "Top":       self.view_xy,
            "Front":     self.view_yz,
            "Left":      self.view_xz,
            "Isometric": self._set_iso,
            "Fit":       self.reset_camera,
        }

    def add_renderer(self, renderer: BaseRenderer):
        """Register a renderer plugin."""
        self._renderers.append(renderer)

    def _set_iso(self):
        self.view_isometric()

    def fit_view(self):
        self.reset_camera()
