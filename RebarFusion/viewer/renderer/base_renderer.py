"""
viewer/renderer/base_renderer.py

Abstract base class for all renderers.
Every renderer plugs into the same SceneManager and PyVista plotter.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

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
        if layer_name and layer_name != self.LAYER_NAME:
            return
        if self.scene.is_visible(self.LAYER_NAME):
            self.clear()
            self.build()
        else:
            self.clear()

    def _on_selection_changed(self):
        # For renderers whose appearance depends on selection, a rebuild is often needed.
        # Triggering a layer change ensures they are rebuilt if visible.
        self._on_layer_changed(self.LAYER_NAME)

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _add_actor(self, actor):
        if actor is not None:
            self._actors.append(actor)
        return actor

    def _apply_scene_transform(self, points, assembly_uuid=None):
        transformed = np.array(points, dtype=float)
        if transformed.size == 0:
            return transformed

        if transformed.ndim != 2:
            transformed = np.reshape(transformed, (-1, 3))
        if transformed.shape[1] < 3:
            padded = np.zeros((transformed.shape[0], 3), dtype=float)
            padded[:, :transformed.shape[1]] = transformed
            transformed = padded

        # Center and scale the model to fit in a unit cube
        if self.scene._model_bounds:
            transformed -= self.scene._model_center
            transformed *= self.scene._model_scale

        # Apply debug Z-scaling
        z_scale = float(getattr(self.scene, "debug_z_scale", 1.0) or 1.0)
        if z_scale != 1.0:
            transformed[:, 2] *= z_scale

        if getattr(self.scene, "debug_exploded_view", False) and assembly_uuid is not None:
            assembly_index = getattr(self.scene, "get_assembly_index", lambda *_: -1)(assembly_uuid)
            if assembly_index >= 0:
                step = float(getattr(self.scene, "debug_explode_step", 250.0) or 250.0)
                # Scale the explosion step relative to the model size
                transformed[:, 2] += assembly_index * step * self.scene._model_scale

        return transformed
