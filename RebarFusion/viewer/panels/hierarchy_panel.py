"""
viewer/panels/hierarchy_panel.py

Project hierarchy panel — shows drawings grouped by floor/element.
Selecting a drawing in the tree filters the viewport.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt

from viewer.scene import SceneManager


class HierarchyPanel(QWidget):
    def __init__(self, scene: SceneManager, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.setMinimumWidth(200)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)

        header = QLabel("PROJECT")
        header.setStyleSheet("font-weight:bold; color:#aaaaaa; font-size:10px; letter-spacing:1px;")
        layout.addWidget(header)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setStyleSheet("""
            QTreeWidget { background:#1c1c2e; border:none; color:#dddddd; font-size:11px; }
            QTreeWidget::item:selected { background:#3a3a5c; }
            QTreeWidget::item:hover { background:#2a2a4a; }
        """)
        layout.addWidget(self._tree)
        self.setLayout(layout)

        scene.on_data_loaded(self._populate)

    def _populate(self):
        self._tree.clear()
        manifest = self.scene.manifest
        if not manifest:
            return

        floors: dict = {}
        for filename, drawing in manifest.drawings.items():
            floor = drawing.identity.floor or "Unknown"
            if floor not in floors:
                floor_item = QTreeWidgetItem([floor])
                floor_item.setForeground(0, Qt.GlobalColor.cyan)
                self._tree.addTopLevelItem(floor_item)
                floors[floor] = floor_item
            child = QTreeWidgetItem([filename])
            floors[floor].addChild(child)

        self._tree.expandAll()
