"""
viewer/panels/console_panel.py

Debug console — shows logs and information about the selected entity.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel
from PySide6.QtGui import QFont
from viewer.scene import SceneManager


class ConsolePanel(QWidget):
    def __init__(self, scene: SceneManager, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.setMinimumHeight(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        font = QFont("Menlo", 10)
        self._output.setFont(font)
        self._output.setStyleSheet(
            "QTextEdit { background:#0d0d1a; color:#a0e0a0; border:none; padding:6px; }"
        )
        layout.addWidget(self._output)
        self.setLayout(layout)

        scene.on_selection_changed(self._refresh)
        self.log("[Engineering Viewer] Ready.")

    def log(self, msg: str):
        self._output.append(msg)

    def _refresh(self):
        scene = self.scene
        lines = []

        if scene.selected_entity_uuid:
            lines.append(f"Selected Entity : {scene.selected_entity_uuid}")
            if scene.graph:
                for e_id, edge in scene.graph.edges.items():
                    if edge.geometry_uuid == scene.selected_entity_uuid:
                        lines.append(f"  Type          : {edge.edge_type}")
                        lines.append(f"  Layer         : {edge.layer}")
                        lines.append(f"  Length        : {edge.length:.2f}")
                        lines.append(f"  Angle         : {edge.angle:.1f}°")
                        lines.append(f"  Edge UUID     : {e_id}")
                        # Nearest component
                        if scene.comp_repo:
                            for cid, comp in scene.comp_repo.components.items():
                                if e_id in comp.edge_ids:
                                    lines.append(f"  Component     : {cid}")
                                    lines.append(f"  Comp Edges    : {len(comp.edge_ids)}")
                                    break
                        break

        if scene.selected_component_uuid:
            comp = scene.comp_repo and scene.comp_repo.components.get(scene.selected_component_uuid)
            if comp:
                lines.append(f"Selected Component : {scene.selected_component_uuid}")
                lines.append(f"  Nodes          : {len(comp.node_ids)}")
                lines.append(f"  Edges          : {len(comp.edge_ids)}")

        if lines:
            self.log("\n".join(lines))
