from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsTextItem, QGraphicsView

from viewer.scene import SceneManager


class Viewport2D(QGraphicsView):
    def __init__(self, scene: SceneManager, parent=None):
        super().__init__(parent)
        self.scene_manager = scene
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#0d0d1a"))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        scene.on_data_loaded(self.rebuild)
        scene.on_layer_changed(lambda *_: self.rebuild())
        scene.on_selection_changed(self.rebuild)
        scene.on_stage_changed(lambda *_: self.rebuild())

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def rebuild(self):
        self._scene.clear()
        s = self.scene_manager
        if s.is_visible(SceneManager.LAYER_GEOMETRY):
            self._draw_geometry()
        if s.is_visible(SceneManager.LAYER_RECOGNITION):
            self._draw_components()
        if s.is_visible(SceneManager.LAYER_FAMILIES):
            self._draw_families()
        if s.is_visible(SceneManager.LAYER_ASSEMBLIES):
            self._draw_assemblies()
        if s.is_visible(SceneManager.LAYER_BARS):
            self._draw_bars()
        if s.is_visible(SceneManager.LAYER_MESHES):
            self._draw_mesh_footprints()
        self._draw_stage_label()
        if not self._scene.items():
            return
        rect = self._scene.itemsBoundingRect().adjusted(-250, -250, 250, 250)
        self._scene.setSceneRect(rect)
        if self.transform().m11() == 1.0:
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _pt(self, point):
        return (float(point[0]), -float(point[1]))

    def _pen(self, color, width=1.0, selected=False, dash=False):
        pen = QPen(QColor(color))
        pen.setWidthF(width * (2.0 if selected else 1.0))
        if dash:
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen

    def _draw_geometry(self):
        repo = self.scene_manager.canon_repo
        if not repo:
            return
        pen = self._pen("#89bfff", 0.8)
        for line in repo.lines:
            x1, y1 = self._pt(line.start)
            x2, y2 = self._pt(line.end)
            self._scene.addLine(x1, y1, x2, y2, pen)
        poly_pen = self._pen("#99dd99", 0.8)
        for poly in repo.polylines:
            for a, b in zip(poly.vertices, poly.vertices[1:]):
                x1, y1 = self._pt(a)
                x2, y2 = self._pt(b)
                self._scene.addLine(x1, y1, x2, y2, poly_pen)
        if self.scene_manager.is_visible(SceneManager.LAYER_TEXT):
            text_pen = QColor("#ffd166")
            for text in repo.texts[:200]:
                item = QGraphicsTextItem(text.text[:24])
                item.setDefaultTextColor(text_pen)
                x, y = self._pt(text.insertion_point)
                item.setPos(x, y)
                item.setScale(8.0)
                self._scene.addItem(item)

    def _draw_components(self):
        graph = self.scene_manager.graph
        comp_repo = self.scene_manager.comp_repo
        if not graph or not comp_repo:
            return
        colors = {
            "straight_bar": "#65d46e",
            "l_bar": "#4da3ff",
            "u_bar": "#4da3ff",
            "stirrup": "#ffd166",
            "branch": "#c084fc",
            "unknown": "#cccccc",
        }
        for comp in comp_repo.components.values():
            result = self.scene_manager.recognition_cache.get(comp.id) if self.scene_manager.recognition_cache else None
            color = colors.get(result.label if result else "unknown", "#cccccc")
            selected = comp.id == self.scene_manager.selected_component_uuid
            pen = self._pen(color, 1.2, selected=selected)
            self._draw_component_edges(comp, graph, pen)

    def _draw_component_edges(self, comp, graph, pen):
        for edge_id in comp.edge_ids:
            edge = graph.edges.get(edge_id)
            if not edge:
                continue
            n1 = graph.nodes.get(edge.start_node_uuid)
            n2 = graph.nodes.get(edge.end_node_uuid)
            if not n1 or not n2:
                continue
            x1, y1 = self._pt(n1.position)
            x2, y2 = self._pt(n2.position)
            self._scene.addLine(x1, y1, x2, y2, pen)

    def _draw_families(self):
        for family in self.scene_manager.engineering_families:
            selected = family.uuid == self.scene_manager.selected_family_uuid
            qa_bad = family.qa and family.qa.warnings
            color = "#65d46e" if family.confidence >= 0.85 and not qa_bad else "#ffd166" if family.confidence >= 0.5 else "#ff4d4d"
            pen = self._pen(color, 2.0, selected=selected)
            members = family.members if self.scene_manager.show_family_expanded else family.members[:1]
            for member in members:
                self._draw_centerline(member.centroid, family.length, family.orientation, pen)
            if self.scene_manager.show_family_missing:
                dash_pen = self._pen("#ff4d4d", 1.5, dash=True)
                self._draw_missing_family_members(family, dash_pen)

    def _draw_assemblies(self):
        for assembly in self.scene_manager.reinforcement_assemblies:
            bb = assembly.bounding_box
            selected = assembly.uuid == self.scene_manager.selected_assembly_uuid
            pen = self._pen("#65d46e", 2.2, selected=selected, dash=True)
            rect = QRectF(bb.min_x, -bb.max_y, bb.max_x - bb.min_x, bb.max_y - bb.min_y)
            self._scene.addRect(rect, pen)

    def _draw_bars(self):
        for bar in self.scene_manager.physical_bars:
            selected = bar.uuid == self.scene_manager.selected_bar_uuid
            pen = self._pen("#f2b84b", max(2.0, bar.diameter / 3.0), selected=selected)
            for a, b in zip(bar.path, bar.path[1:]):
                x1, y1 = self._pt(a)
                x2, y2 = self._pt(b)
                self._scene.addLine(x1, y1, x2, y2, pen)

    def _draw_mesh_footprints(self):
        for mesh in self.scene_manager.reconstruction_meshes:
            selected = mesh.uuid == self.scene_manager.selected_mesh_uuid
            pen = self._pen("#d0d0d8", 0.6, selected=selected)
            for a, b, c in mesh.faces[::4]:
                pts = [mesh.vertices[a], mesh.vertices[b], mesh.vertices[c], mesh.vertices[a]]
                for p1, p2 in zip(pts, pts[1:]):
                    x1, y1 = self._pt(p1)
                    x2, y2 = self._pt(p2)
                    self._scene.addLine(x1, y1, x2, y2, pen)

    def _draw_centerline(self, centroid, length, orientation, pen):
        angle = math.radians(orientation)
        ax, ay = math.cos(angle), math.sin(angle)
        half = length / 2.0
        cx, cy = centroid
        x1, y1 = self._pt((cx - ax * half, cy - ay * half))
        x2, y2 = self._pt((cx + ax * half, cy + ay * half))
        self._scene.addLine(x1, y1, x2, y2, pen)

    def _draw_missing_family_members(self, family, pen):
        if not family.members:
            return
        rep = family.members[0]
        angle = math.radians(family.orientation)
        px, py = -math.sin(angle), math.cos(angle)
        for offset in family.missing_member_offsets:
            cx = rep.centroid[0] + px * offset
            cy = rep.centroid[1] + py * offset
            self._draw_centerline((cx, cy), family.length, family.orientation, pen)

    def _draw_stage_label(self):
        item = QGraphicsTextItem(f"Stage: {self.scene_manager.current_stage}")
        item.setDefaultTextColor(QColor("#dddddd"))
        item.setPos(20, 20)
        item.setScale(16.0)
        self._scene.addItem(item)
