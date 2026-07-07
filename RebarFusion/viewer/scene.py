"""
viewer/scene.py

SceneManager — the single shared scene state for the Engineering Viewer.
Every renderer reads and writes to this object. Nothing bypasses it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from uuid import UUID


@dataclass
class LayerState:
    """Toggle and visual parameters for a named rendering layer."""
    visible: bool = True
    opacity: float = 1.0
    color: str = "#ffffff"


class SceneManager:
    """
    Central scene state shared by all renderers and panels.

    Responsibilities
    ----------------
    - Store all loaded repositories (Geometry, Nodes, Graph, …)
    - Maintain per-layer visibility state
    - Track which entity/component is currently selected
    - Publish change notifications via simple callback lists

    Nothing in the viewer draws without going through SceneManager.
    """

    # Layer names — renderers register themselves here
    LAYER_GEOMETRY  = "Geometry"
    LAYER_NODES     = "Nodes"
    LAYER_GRAPH     = "Graph"
    LAYER_COMPONENTS = "Components"
    LAYER_BBOXES    = "Bounding Boxes"
    LAYER_LABELS    = "Labels"
    LAYER_DIMS      = "Dimensions"
    LAYER_TEXT      = "Text"
    LAYER_RECOGNITION = "Recognition"
    LAYER_CONFIDENCE  = "Confidence"

    DEFAULT_LAYERS = [
        LAYER_GEOMETRY,
        LAYER_NODES,
        LAYER_GRAPH,
        LAYER_COMPONENTS,
        LAYER_BBOXES,
        LAYER_LABELS,
        LAYER_DIMS,
        LAYER_TEXT,
        LAYER_RECOGNITION,
        LAYER_CONFIDENCE,
    ]

    def __init__(self):
        # Repositories (set by the app after loading a project)
        self.manifest = None
        self.canon_repo = None
        self.node_repo = None
        self.graph = None
        self.comp_repo = None
        self.recognition_cache = None

        # Layer states
        self.layers: Dict[str, LayerState] = {
            name: LayerState(visible=(name == self.LAYER_GEOMETRY))
            for name in self.DEFAULT_LAYERS
        }

        # Selection
        self.selected_entity_uuid: Optional[UUID] = None
        self.selected_component_uuid: Optional[UUID] = None

        # Change listeners: functions called with (scene_manager)
        self._on_data_loaded_callbacks: List = []
        self._on_layer_changed_callbacks: List = []
        self._on_selection_changed_callbacks: List = []

    # ─── Data loading ────────────────────────────────────────────────────────

    def load(self, manifest=None, canon_repo=None, node_repo=None, graph=None, comp_repo=None):
        self.manifest = manifest
        self.canon_repo = canon_repo
        self.node_repo = node_repo
        self.graph = graph
        self.comp_repo = comp_repo
        self._fire(self._on_data_loaded_callbacks)

    # ─── Layer management ─────────────────────────────────────────────────────

    def set_layer_visible(self, name: str, visible: bool):
        if name in self.layers:
            self.layers[name].visible = visible
            self._fire(self._on_layer_changed_callbacks, name)

    def is_visible(self, name: str) -> bool:
        return self.layers.get(name, LayerState()).visible

    # ─── Selection ────────────────────────────────────────────────────────────

    def select_entity(self, entity_uuid: Optional[UUID]):
        self.selected_entity_uuid = entity_uuid
        self._fire(self._on_selection_changed_callbacks)

    def select_component(self, comp_uuid: Optional[UUID]):
        self.selected_component_uuid = comp_uuid
        self._fire(self._on_selection_changed_callbacks)

    def clear_selection(self):
        self.selected_entity_uuid = None
        self.selected_component_uuid = None
        self._fire(self._on_selection_changed_callbacks)

    # ─── Event system ─────────────────────────────────────────────────────────

    def on_data_loaded(self, callback):
        self._on_data_loaded_callbacks.append(callback)

    def on_layer_changed(self, callback):
        self._on_layer_changed_callbacks.append(callback)

    def on_selection_changed(self, callback):
        self._on_selection_changed_callbacks.append(callback)

    def _fire(self, callbacks, *args):
        for cb in callbacks:
            try:
                cb(*args)
            except Exception as e:
                print(f"[SceneManager] Callback error: {e}")
