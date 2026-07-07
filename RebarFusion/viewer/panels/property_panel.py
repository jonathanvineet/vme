"""
viewer/panels/property_panel.py

Properties panel — shows UUID, Layer, Length, Angle, Bounding Box, etc.
Updated whenever SceneManager fires a selection_changed event.
"""
from __future__ import annotations

from typing import Any, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QFrame, QScrollArea
)
from PySide6.QtCore import Qt

from viewer.scene import SceneManager


class PropertyPanel(QWidget):
    def __init__(self, scene: SceneManager, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.setMinimumWidth(220)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; background:#161625; }")

        inner = QWidget()
        inner.setStyleSheet("background:#161625;")
        self._form = QFormLayout(inner)
        self._form.setContentsMargins(8, 8, 8, 8)
        self._form.setSpacing(5)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.setLayout(outer)

        # Default placeholder
        self._show({"Status": "Nothing selected"})

        scene.on_selection_changed(self._on_selection)

    def _clear(self):
        while self._form.rowCount():
            self._form.removeRow(0)

    def _show(self, data: Dict[str, Any]):
        self._clear()
        for key, val in data.items():
            lbl_key = QLabel(str(key))
            lbl_key.setStyleSheet("color:#8888aa; font-size:10px; font-weight:bold;")
            lbl_val = QLabel(str(val))
            lbl_val.setStyleSheet("color:#dddddd; font-size:11px;")
            lbl_val.setWordWrap(True)
            self._form.addRow(lbl_key, lbl_val)

    def _on_selection(self):
        scene = self.scene
        data: Dict[str, Any] = {}

        if scene.selected_mesh_uuid is not None:
            mesh = None
            for candidate in getattr(scene, "reconstruction_meshes", []) or []:
                if candidate.uuid == scene.selected_mesh_uuid:
                    mesh = candidate
                    break
            if mesh:
                data["Type"] = "Reconstruction Mesh"
                data["UUID"] = str(mesh.uuid)[:12] + "…"
                data["Bar"] = str(mesh.bar_uuid)[:12] + "…"
                data["Vertices"] = len(mesh.vertices)
                data["Faces"] = len(mesh.faces)
                data["Confidence"] = f"{mesh.confidence:.2f}"
                data["Provenance"] = "Mesh -> Physical Bar -> Family -> Components -> CAD"

        elif scene.selected_bar_uuid is not None:
            bar = None
            for candidate in getattr(scene, "physical_bars", []) or []:
                if candidate.uuid == scene.selected_bar_uuid:
                    bar = candidate
                    break
            if bar:
                data["Type"] = "Physical Bar"
                data["Mark"] = bar.mark
                data["UUID"] = str(bar.uuid)[:12] + "…"
                data["Family"] = str(bar.family_uuid)[:12] + "…"
                data["Diameter"] = f"Ø{bar.diameter:g}"
                data["Radius"] = f"{bar.radius:.1f} mm"
                data["Path Points"] = len(bar.centerline.points)
                data["Bends"] = len(bar.centerline.bends)
                data["Hooks"] = len(bar.centerline.hooks)
                data["Layer"] = str(bar.layer_uuid)[:12] + "…" if bar.layer_uuid else "None"
                data["Adjustments"] = ", ".join(bar.adjustment_notes)
                data["Confidence"] = f"{bar.confidence:.2f}"
                data["Provenance"] = "Physical Bar -> Family -> Components -> CAD"

        elif scene.selected_assembly_uuid is not None:
            assembly = None
            for candidate in getattr(scene, "reinforcement_assemblies", []) or []:
                if candidate.uuid == scene.selected_assembly_uuid:
                    assembly = candidate
                    break

            if assembly:
                frame = assembly.local_coordinate_system
                data["Type"] = "Reinforcement Assembly"
                data["Assembly"] = assembly.assembly_type
                data["UUID"] = str(assembly.uuid)[:12] + "…"
                data["Families"] = len(assembly.families)
                data["Layers"] = len(assembly.layers)
                data["Bars"] = len(assembly.bars)
                data["Cover"] = f"{frame.cover:.1f} mm"
                data["Thickness"] = f"{frame.thickness:.1f} mm"
                data["Confidence"] = f"{assembly.confidence:.2f}"
                if assembly.layers:
                    data["Layer Names"] = ", ".join(layer.name for layer in assembly.layers)
                data["Provenance"] = "Assembly -> Families -> Bars -> Meshes"

        elif scene.selected_family_uuid is not None:
            family = None
            for candidate in getattr(scene, "engineering_families", []) or []:
                if candidate.uuid == scene.selected_family_uuid:
                    family = candidate
                    break

            if family:
                missing = family.qa.missing_members if family.qa and family.qa.missing_members is not None else 0
                data["Type"] = "Engineering Family"
                data["Family"] = family.mark
                data["Family Type"] = family.family_type
                data["UUID"] = str(family.uuid)[:12] + "…"
                data["Diameter"] = f"Ø{family.diameter:g}" if family.diameter else "Unknown"
                data["Spacing"] = f"{family.spacing:g} c/c" if family.spacing else "Unknown"
                data["Spacing Source"] = family.spacing_source
                data["Members"] = family.estimated_count or family.detected_count
                data["Detected"] = family.detected_count
                data["Missing"] = missing
                data["Length"] = f"{family.length:.1f} mm"
                data["Dominant Direction"] = f"{family.dominant_direction:.1f}° {family.dominant_direction_label}"
                data["Normal Direction"] = f"{family.normal_direction:.1f}° {family.normal_direction_label}"
                data["Confidence"] = f"{family.confidence:.2f}"
                if family.qa and family.qa.warnings:
                    data["QA"] = ", ".join(family.qa.warnings)
                data["Provenance"] = "Family -> Members -> Components -> CAD"
                if family.evidence:
                    data["Evidence"] = "; ".join(e.rule for e in family.evidence[:3])

        elif scene.selected_component_uuid is not None:
            comp = scene.comp_repo and scene.comp_repo.components.get(scene.selected_component_uuid)
            if comp:
                data["Type"] = "Component"
                data["UUID"] = str(comp.id)[:12] + "…"
                data["Nodes"] = comp.statistics.get("node_count", 0)
                data["Edges"] = comp.statistics.get("edge_count", 0)
                data["Total Length"] = f"{comp.statistics.get('total_length',0):.1f}"
                data["Avg Degree"] = f"{comp.statistics.get('average_degree',0):.2f}"
                bb = comp.bbox
                data["BBox"] = f"({bb[0]:.0f},{bb[1]:.0f}) → ({bb[2]:.0f},{bb[3]:.0f})"
                
                # Associated engineering object
                if hasattr(scene, 'recognition_cache') and scene.recognition_cache:
                    res = scene.recognition_cache.get(comp.id)
                    if res:
                        data["Recognized Shape"] = res.label
                        
                # Phase 8 Association Results
                if hasattr(scene, 'engineering_objects') and scene.engineering_objects:
                    obj = scene.engineering_objects.get(comp.id)
                    if obj:
                        data["Engineering Object"] = obj.object_type
                        if hasattr(obj, 'mark') and obj.mark:
                            data["  Mark"] = obj.mark
                        if hasattr(obj, 'diameter') and obj.diameter:
                            data["  Diameter"] = f"Ø{obj.diameter}"
                        if hasattr(obj, 'spacing') and obj.spacing:
                            data["  Spacing"] = f"{obj.spacing} c/c"
                        if hasattr(obj, 'length') and obj.length:
                            data["  Length"] = f"{obj.length} mm"

                families = []
                for family in getattr(scene, "engineering_families", []) or []:
                    if comp.id in family.member_component_uuids:
                        families.append(f"{family.mark} ({family.detected_count})")
                if families:
                    data["Engineering Family"] = ", ".join(families)

        elif scene.selected_entity_uuid is not None:
            uid = scene.selected_entity_uuid
            data["UUID"] = str(uid)[:12] + "…"
            # Try to find in graph edges
            if scene.graph and uid in scene.graph.edges:
                edge = scene.graph.edges[uid]
                data["Type"] = f"Edge ({edge.edge_type})"
                data["Layer"] = edge.layer
                data["Length"] = f"{edge.length:.1f}"
            else:
                data["Type"] = "Entity"
        else:
            data["Status"] = "Nothing selected"

        self._show(data)
