from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from viewer.scene import SceneManager


class ProjectTreePanel(QWidget):
    def __init__(self, scene: SceneManager, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.setMinimumWidth(240)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)

        header = QLabel("PROJECT TREE")
        header.setStyleSheet("font-weight:bold; color:#aaaaaa; font-size:10px; letter-spacing:1px;")
        layout.addWidget(header)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setStyleSheet(
            """
            QTreeWidget { background:#1c1c2e; border:none; color:#dddddd; font-size:11px; }
            QTreeWidget::item:selected { background:#3a3a5c; }
            QTreeWidget::item:hover { background:#2a2a4a; }
            """
        )
        layout.addWidget(self._tree)
        self.setLayout(layout)

        self._tree.itemClicked.connect(self._on_item_clicked)
        scene.on_data_loaded(self._populate)
        scene.on_selection_changed(self._sync_selection)

    def _populate(self):
        self._tree.clear()

        manifest = self.scene.manifest
        root = QTreeWidgetItem(["Project"])
        root.setForeground(0, Qt.GlobalColor.cyan)
        self._tree.addTopLevelItem(root)

        if manifest:
            project_item = QTreeWidgetItem([manifest.project_name])
            root.addChild(project_item)
            drawings_root = QTreeWidgetItem(["Drawings"])
            project_item.addChild(drawings_root)
            for filename, drawing in manifest.drawings.items():
                label = f"{filename}"
                if drawing.duplicate_of:
                    label += " (duplicate)"
                drawing_item = QTreeWidgetItem([label])
                drawing_item.setData(0, Qt.ItemDataRole.UserRole, ("drawing", filename))
                drawings_root.addChild(drawing_item)

        bundle = getattr(self.scene, "project_data", None)
        if not bundle:
            self._tree.expandAll()
            return

        drawing_root = QTreeWidgetItem([f"Loaded: {bundle.drawing_name}"])
        drawing_root.setForeground(0, Qt.GlobalColor.yellow)
        root.addChild(drawing_root)

        self._add_count_node(drawing_root, "Geometry", [
            ("Lines", len(getattr(bundle.canon_repo, "lines", []) or [])),
            ("Arcs", len(getattr(bundle.canon_repo, "arcs", []) or [])),
            ("Polylines", len(getattr(bundle.canon_repo, "polylines", []) or [])),
            ("Circles", len(getattr(bundle.canon_repo, "circles", []) or [])),
            ("Texts", len(getattr(bundle.canon_repo, "texts", []) or [])),
            ("MTexts", len(getattr(bundle.canon_repo, "mtexts", []) or [])),
            ("Dimensions", len(getattr(bundle.canon_repo, "dimensions", []) or [])),
        ])

        topology_root = QTreeWidgetItem(["Topology"])
        drawing_root.addChild(topology_root)
        self._add_count_node(topology_root, "Nodes", [("Nodes", len(getattr(bundle.node_repo, "nodes", {}) or {}))])
        self._add_count_node(topology_root, "Edges", [("Edges", len(getattr(bundle.graph, "edges", {}) or {}))])
        components_node = QTreeWidgetItem([f"Components ({len(getattr(bundle.comp_repo, 'components', {}) or {})})"])
        topology_root.addChild(components_node)
        for comp_uuid, comp in sorted((getattr(bundle.comp_repo, "components", {}) or {}).items(), key=lambda item: str(item[0])):
            label = f"{str(comp_uuid)[:8]}  ({len(getattr(comp, 'edge_ids', []) or [])} edges)"
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, ("component", comp_uuid))
            components_node.addChild(item)

        recognition_root = QTreeWidgetItem([f"Recognition ({len(bundle.recognition_cache)})"])
        drawing_root.addChild(recognition_root)
        for comp_uuid, result in sorted(bundle.recognition_cache.items(), key=lambda item: str(item[0])):
            label = f"{str(comp_uuid)[:8]}  {getattr(result, 'label', 'unknown')}  {getattr(result, 'confidence', 0.0):.2f}"
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, ("component", comp_uuid))
            recognition_root.addChild(item)

        families_root = QTreeWidgetItem([f"Families ({len(bundle.engineering_families)})"])
        drawing_root.addChild(families_root)
        for family in bundle.engineering_families:
            item = QTreeWidgetItem([f"{family.mark}  Ø{getattr(family, 'diameter', 0)}  {getattr(family, 'detected_count', 0)} bars"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("family", family.uuid))
            families_root.addChild(item)

        assemblies_root = QTreeWidgetItem([f"Assemblies ({len(bundle.reinforcement_assemblies)})"])
        drawing_root.addChild(assemblies_root)
        for assembly in bundle.reinforcement_assemblies:
            item = QTreeWidgetItem([f"{assembly.assembly_type}  ({len(getattr(assembly, 'bars', []) or [])} bars)"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("assembly", assembly.uuid))
            assemblies_root.addChild(item)

        bars_root = QTreeWidgetItem([f"Bars ({len(bundle.physical_bars)})"])
        drawing_root.addChild(bars_root)
        for bar in bundle.physical_bars:
            item = QTreeWidgetItem([f"{bar.mark}  Ø{getattr(bar, 'diameter', 0)}"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("bar", bar.uuid))
            bars_root.addChild(item)

        meshes_root = QTreeWidgetItem([f"Meshes ({len(bundle.reconstruction_meshes)})"])
        drawing_root.addChild(meshes_root)
        for mesh in bundle.reconstruction_meshes:
            item = QTreeWidgetItem([f"mesh  {len(getattr(mesh, 'vertices', []) or [])}v/{len(getattr(mesh, 'faces', []) or [])}f"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("mesh", mesh.uuid))
            meshes_root.addChild(item)

        qa_root = QTreeWidgetItem(["QA / Reports"])
        drawing_root.addChild(qa_root)
        for report_name, report in bundle.phase_reports.items():
            item = QTreeWidgetItem([report_name])
            item.setData(0, Qt.ItemDataRole.UserRole, ("report", report_name))
            qa_root.addChild(item)

        self._tree.expandAll()

    def _add_count_node(self, parent: QTreeWidgetItem, label: str, rows):
        node = QTreeWidgetItem([label])
        parent.addChild(node)
        for row_label, value in rows:
            node.addChild(QTreeWidgetItem([f"{row_label}: {value}"]))

    def _sync_selection(self):
        # Placeholder for future two-way sync; the tree selection is driven by click handlers.
        pass

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
        elif kind == "component":
            self.scene.select_component(value)
