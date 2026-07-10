"""
viewer/scene.py

SceneManager — the single shared scene state for the Engineering Viewer.
Every renderer reads and writes to this object. Nothing bypasses it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from viewer.workbench_project import WorkbenchProject


@dataclass
class LayerState:
    """Toggle and visual parameters for a named rendering layer."""
    visible: bool = True,
    opacity: float = 1.0,
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
    LAYER_FAMILIES    = "Families"
    LAYER_ASSEMBLIES  = "Assemblies"
    LAYER_BARS        = "Bars"
    LAYER_MESHES      = "Meshes"
    LAYER_QA          = "QA"

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
        LAYER_FAMILIES,
        LAYER_ASSEMBLIES,
        LAYER_BARS,
        LAYER_MESHES,
        LAYER_QA,
    ]

    STAGES = [
        "Geometry",
        "Recognition",
        "Families",
        "Assemblies",
        "Bars",
        "Meshes",
    ]

    def __init__(self):
        # Repositories (set by the app after loading a project)
        self.project: Optional[WorkbenchProject] = None
        self.manifest = None
        self.canon_repo = None
        self.node_repo = None
        self.graph = None
        self.comp_repo = None
        self.recognition_cache = None
        self.engineering_objects = {}
        self.engineering_families = []
        self.reinforcement_assemblies = []
        self.physical_bars = []
        self.reconstruction_meshes = []
        self.current_stage = "Meshes"
        self.show_family_representative = False
        self.show_family_expanded = True
        self.show_family_missing = True
        self.show_family_qa = True

        # Layer states
        self.layers: Dict[str, LayerState] = {
            name: LayerState(visible=(name == self.LAYER_GEOMETRY))
            for name in self.DEFAULT_LAYERS
        }

        # Selection
        self.selected_entity_uuid: Optional[UUID] = None
        self.selected_component_uuid: Optional[UUID] = None
        self.selected_family_uuid: Optional[UUID] = None
        self.selected_assembly_uuid: Optional[UUID] = None
        self.selected_bar_uuid: Optional[UUID] = None
        self.selected_mesh_uuid: Optional[UUID] = None

        # Change listeners: functions called with (scene_manager)
        self._on_data_loaded_callbacks: List = []
        self._on_layer_changed_callbacks: List = []
        self._on_selection_changed_callbacks: List = []
        self._on_stage_changed_callbacks: List = []

    # ─── Data loading ────────────────────────────────────────────────────────

    def load_project(self, project: WorkbenchProject):
        """Loads all data from a single unified project object."""
        self.project = project
        self.manifest = project.manifest
        self.canon_repo = project.canon_repo
        self.node_repo = project.node_repo
        self.graph = project.graph
        self.comp_repo = project.comp_repo
        self.recognition_cache = project.recognition_cache
        self.engineering_objects = project.engineering_objects
        self.engineering_families = project.engineering_families
        self.reinforcement_assemblies = project.reinforcement_assemblies
        self.physical_bars = project.physical_bars
        self.reconstruction_meshes = project.reconstruction_meshes

        # Legacy project data property for panels that might still use it
        self.project_data = getattr(project, 'bundle', None)

        self.clear_selection()
        self._fire(self._on_data_loaded_callbacks)

    # ─── Layer management ─────────────────────────────────────────────────────

    def set_layer_visible(self, name: str, visible: bool):
        if name in self.layers:
            self.layers[name].visible = visible
            self._fire(self._on_layer_changed_callbacks, name)

    def set_family_display_option(self, name: str, visible: bool):
        if name == "representative":
            self.show_family_representative = visible
        elif name == "expanded":
            self.show_family_expanded = visible
        elif name == "missing":
            self.show_family_missing = visible
        elif name == "qa":
            self.show_family_qa = visible
        self._fire(self._on_layer_changed_callbacks, self.LAYER_FAMILIES)

    def set_stage(self, stage: str):
        if stage not in self.STAGES:
            return
        self.current_stage = stage
        visible_layers = {
            "Geometry": {self.LAYER_GEOMETRY, self.LAYER_TEXT, self.LAYER_DIMS},
            "Recognition": {self.LAYER_GEOMETRY, self.LAYER_RECOGNITION},
            "Families": {self.LAYER_GEOMETRY, self.LAYER_FAMILIES, self.LAYER_QA},
            "Assemblies": {self.LAYER_FAMILIES, self.LAYER_ASSEMBLIES, self.LAYER_QA},
            "Bars": {self.LAYER_FAMILIES, self.LAYER_ASSEMBLIES, self.LAYER_BARS},
            "Meshes": {self.LAYER_BARS, self.LAYER_MESHES},
        }[stage]
        for name in self.layers:
            self.layers[name].visible = name in visible_layers
        self._fire(self._on_stage_changed_callbacks, stage)
        self._fire(self._on_layer_changed_callbacks, "")

    def is_visible(self, name: str) -> bool:
        return self.layers.get(name, LayerState()).visible

    # ─── Selection ────────────────────────────────────────────────────────────

    def select_entity(self, entity_uuid: Optional[UUID]):
        self.selected_entity_uuid = entity_uuid
        self.selected_component_uuid = None
        self.selected_family_uuid = None
        self.selected_assembly_uuid = None
        self.selected_bar_uuid = None
        self.selected_mesh_uuid = None
        self._fire(self._on_selection_changed_callbacks)

    def select_component(self, comp_uuid: Optional[UUID]):
        self.selected_component_uuid = comp_uuid
        self.selected_family_uuid = None
        self.selected_assembly_uuid = None
        self.selected_bar_uuid = None
        self.selected_mesh_uuid = None
        self._fire(self._on_selection_changed_callbacks)

    def select_family(self, family_uuid: Optional[UUID]):
        self.selected_entity_uuid = None
        self.selected_component_uuid = None
        self.selected_family_uuid = family_uuid
        self.selected_assembly_uuid = None
        self.selected_bar_uuid = None
        self.selected_mesh_uuid = None
        self._fire(self._on_selection_changed_callbacks)

    def select_assembly(self, assembly_uuid: Optional[UUID]):
        self.selected_entity_uuid = None
        self.selected_component_uuid = None
        self.selected_family_uuid = None
        self.selected_assembly_uuid = assembly_uuid
        self.selected_bar_uuid = None
        self.selected_mesh_uuid = None
        self._fire(self._on_selection_changed_callbacks)

    def select_bar(self, bar_uuid: Optional[UUID]):
        self.selected_entity_uuid = None
        self.selected_component_uuid = None
        self.selected_assembly_uuid = None
        self.selected_bar_uuid = bar_uuid
        self.selected_mesh_uuid = None
        self.selected_family_uuid = None
        for bar in self.physical_bars:
            if bar.uuid == bar_uuid:
                self.selected_family_uuid = bar.family_uuid
                break
        self._fire(self._on_selection_changed_callbacks)

    def select_mesh(self, mesh_uuid: Optional[UUID]):
        self.selected_entity_uuid = None
        self.selected_component_uuid = None
        self.selected_assembly_uuid = None
        self.selected_mesh_uuid = mesh_uuid
        self.selected_bar_uuid = None
        self.selected_family_uuid = None
        for mesh in self.reconstruction_meshes:
            if mesh.uuid == mesh_uuid:
                self.selected_bar_uuid = mesh.bar_uuid
                break
        if self.selected_bar_uuid:
            for bar in self.physical_bars:
                if bar.uuid == self.selected_bar_uuid:
                    self.selected_family_uuid = bar.family_uuid
                    break
        self._fire(self._on_selection_changed_callbacks)

    def clear_selection(self):
        self.selected_entity_uuid = None
        self.selected_component_uuid = None
        self.selected_family_uuid = None
        self.selected_assembly_uuid = None
        self.selected_bar_uuid = None
        self.selected_mesh_uuid = None
        self._fire(self._on_selection_changed_callbacks)

    def search(self, query: str) -> bool:
        q = query.strip().lower()
        if not q:
            return False
        for family in self.engineering_families:
            if q == str(family.mark).lower() or q in str(family.uuid).lower() or q in str(getattr(family, "family_type", "")).lower():
                self.select_family(family.uuid)
                return True
        for assembly in self.reinforcement_assemblies:
            if q in assembly.assembly_type.lower() or q in str(assembly.uuid).lower():
                self.select_assembly(assembly.uuid)
                return True
        for bar in self.physical_bars:
            if q == str(bar.mark).lower() or q in str(bar.uuid).lower() or q in str(getattr(bar, "bar_type", "")).lower():
                self.select_bar(bar.uuid)
                return True
        for mesh in self.reconstruction_meshes:
            if q in str(mesh.uuid).lower() or q in str(mesh.bar_uuid).lower():
                self.select_mesh(mesh.uuid)
                return True
        for comp_uuid, result in (self.recognition_cache or {}).items():
            if q in str(comp_uuid).lower() or q in str(getattr(result, "label", "")).lower():
                self.select_component(comp_uuid)
                return True
        return False

    # ─── Event system ─────────────────────────────────────────────────────────

    def on_data_loaded(self, callback):
        self._on_data_loaded_callbacks.append(callback)

    def on_layer_changed(self, callback):
        self._on_layer_changed_callbacks.append(callback)

    def on_selection_changed(self, callback):
        self._on_selection_changed_callbacks.append(callback)

    def on_stage_changed(self, callback):
        self._on_stage_changed_callbacks.append(callback)

    def _fire(self, callbacks, *args):
        for cb in callbacks:
            try:
                cb(*args)
            except Exception as e:
                print(f"[SceneManager] Callback error: {e}")
