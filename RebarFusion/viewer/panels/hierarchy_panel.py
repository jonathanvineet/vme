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

        self._tree.itemClicked.connect(self._on_item_clicked)
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

        families = getattr(self.scene, "engineering_families", None) or []
        if families:
            family_root = QTreeWidgetItem(["Engineering Families"])
            family_root.setForeground(0, Qt.GlobalColor.yellow)
            self._tree.addTopLevelItem(family_root)
            for family in families:
                item = QTreeWidgetItem([f"{family.mark}  ({family.detected_count} members)"])
                item.setData(0, Qt.ItemDataRole.UserRole, ("family", family.uuid))
                family_root.addChild(item)

        assemblies = getattr(self.scene, "reinforcement_assemblies", None) or []
        if assemblies:
            assembly_root = QTreeWidgetItem(["Reinforcement Assemblies"])
            assembly_root.setForeground(0, Qt.GlobalColor.green)
            self._tree.addTopLevelItem(assembly_root)
            for assembly in assemblies:
                item = QTreeWidgetItem([f"{assembly.assembly_type}  ({len(assembly.bars)} bars)"])
                item.setData(0, Qt.ItemDataRole.UserRole, ("assembly", assembly.uuid))
                assembly_root.addChild(item)

        bars = getattr(self.scene, "physical_bars", None) or []
        if bars:
            bar_root = QTreeWidgetItem(["Physical Bars"])
            bar_root.setForeground(0, Qt.GlobalColor.magenta)
            self._tree.addTopLevelItem(bar_root)
            for bar in bars[:250]:
                item = QTreeWidgetItem([f"{bar.mark}  Ø{bar.diameter:g}"])
                item.setData(0, Qt.ItemDataRole.UserRole, ("bar", bar.uuid))
                bar_root.addChild(item)

        meshes = getattr(self.scene, "reconstruction_meshes", None) or []
        if meshes:
            mesh_root = QTreeWidgetItem(["Meshes"])
            mesh_root.setForeground(0, Qt.GlobalColor.lightGray)
            self._tree.addTopLevelItem(mesh_root)
            for mesh in meshes[:250]:
                item = QTreeWidgetItem([f"mesh  {len(mesh.vertices)}v/{len(mesh.faces)}f"])
                item.setData(0, Qt.ItemDataRole.UserRole, ("mesh", mesh.uuid))
                mesh_root.addChild(item)

        self._tree.expandAll()

    def _on_item_clicked(self, item, column):
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if not payload:
            return
        kind, value = payload
        if kind == "family":
            self.scene.select_family(value)
        elif kind == "assembly":
            self.scene.select_assembly(value)
        elif kind == "bar":
            self.scene.select_bar(value)
        elif kind == "mesh":
            self.scene.select_mesh(value)
