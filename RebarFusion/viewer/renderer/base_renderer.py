"""
viewer/renderer/base_renderer.py

Abstract base class for all renderers.
Every renderer plugs into the same SceneManager and PyVista plotter.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyvista as pv
    from viewer.scene import SceneManager


class BaseRenderer(ABC):
    """
    Interface contract for all Engineering Viewer renderers.

    Lifecycle
    ---------
    1. `__init__(scene, plotter)` — store refs, connect to scene events
    2. `build()` — first-time mesh construction, called after data is loaded
    3. `refresh()` — lightweight redraw on layer/selection changes
    4. `clear()` — remove all owned actors from the plotter
    """

    # Override in subclass — used for logging and layer lookup
    LAYER_NAME: str = ""

    def __init__(self, scene: "SceneManager", plotter: "pv.Plotter"):
        self.scene = scene
        self.plotter = plotter
        self._actors = []

        # Auto-subscribe to scene events
        scene.on_data_loaded(self._on_data_loaded)
        scene.on_layer_changed(self._on_layer_changed)
        scene.on_selection_changed(self._on_selection_changed)

    # ─── Required overrides ───────────────────────────────────────────────

    @abstractmethod
    def build(self):
        """Construct meshes and add actors to the plotter. Called once per data load."""
        pass

    # ─── Optional overrides ───────────────────────────────────────────────

    def refresh(self):
        """Called when selection changes. Re-color or re-render as needed."""
        pass

    def clear(self):
        """Remove all actors owned by this renderer."""
        for actor in self._actors:
            try:
                self.plotter.remove_actor(actor)
            except Exception:
                pass
        self._actors.clear()

    # ─── Scene event hooks ────────────────────────────────────────────────

    def _on_data_loaded(self):
        self.clear()
        if self.LAYER_NAME and not self.scene.is_visible(self.LAYER_NAME):
            return
        self.build()

    def _on_layer_changed(self, layer_name: str = ""):
        if layer_name != self.LAYER_NAME:
            return
        if self.scene.is_visible(self.LAYER_NAME):
            self.build()
        else:
            self.clear()

    def _on_selection_changed(self):
        self.refresh()

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _add_actor(self, actor):
        if actor is not None:
            self._actors.append(actor)
        return actor
