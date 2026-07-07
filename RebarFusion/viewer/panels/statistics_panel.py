"""
viewer/panels/statistics_panel.py

Statistics panel — live project/graph metrics summary.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from viewer.scene import SceneManager


def _stat_row(label: str, value: str) -> QLabel:
    lbl = QLabel(f"<b style='color:#8888aa;'>{label}</b><br><span style='color:#dddddd;font-size:13px;'>{value}</span>")
    lbl.setStyleSheet("padding:4px 0;")
    return lbl


class StatisticsPanel(QWidget):
    def __init__(self, scene: SceneManager, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.setMinimumWidth(180)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(2)

        hdr = QLabel("STATISTICS")
        hdr.setStyleSheet("font-weight:bold; color:#aaaaaa; font-size:10px; letter-spacing:1px;")
        self._layout.addWidget(hdr)
        self._layout.addStretch()
        self.setLayout(self._layout)

        scene.on_data_loaded(self._refresh)

    def _clear(self):
        while self._layout.count() > 2:  # keep header and stretch
            item = self._layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

    def _refresh(self):
        self._clear()

        scene = self.scene
        stats = {}

        if scene.canon_repo:
            stats["Lines"] = len(scene.canon_repo.lines)
            stats["Arcs"] = len(scene.canon_repo.arcs)
            stats["Polylines"] = len(scene.canon_repo.polylines)
            stats["Circles"] = len(scene.canon_repo.circles)

        if scene.node_repo:
            stats["Nodes"] = len(scene.node_repo.nodes)

        if scene.graph:
            stats["Edges"] = len(scene.graph.edges)

        if scene.comp_repo:
            stats["Components"] = len(scene.comp_repo.components)

        stats["Families"] = len(getattr(scene, "engineering_families", []) or [])
        stats["Assemblies"] = len(getattr(scene, "reinforcement_assemblies", []) or [])
        stats["Bars"] = len(getattr(scene, "physical_bars", []) or [])
        stats["Meshes"] = len(getattr(scene, "reconstruction_meshes", []) or [])
        stats["Vertices"] = sum(len(mesh.vertices) for mesh in getattr(scene, "reconstruction_meshes", []) or [])
        stats["Faces"] = sum(len(mesh.faces) for mesh in getattr(scene, "reconstruction_meshes", []) or [])
        stats["QA Warnings"] = sum(
            len(f.qa.warnings)
            for f in getattr(scene, "engineering_families", []) or []
            if getattr(f, "qa", None)
        )

        insert_pos = 1
        for k, v in stats.items():
            row = _stat_row(k, str(v))
            self._layout.insertWidget(insert_pos, row)
            insert_pos += 1
