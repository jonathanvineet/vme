"""
viewer/app.py

RebarFusion Engineering Viewer — main application window.

Architecture
------------
  MainWindow
  ├── Menu Bar (File, View, Layers, Debug)
  ├── Toolbar (camera presets, open project)
  ├── Left Dock  → HierarchyPanel + StatisticsPanel
  ├── Centre     → ViewportWidget (PyVista / pyvistaqt)
  ├── Right Dock → LayerPanel + PropertyPanel
  └── Bottom Dock → ConsolePanel

All data flows through SceneManager. Renderers are plugins.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDockWidget,
    QToolBar, QStatusBar, QWidget, QVBoxLayout, QLabel, QFileDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon

from viewer.scene import SceneManager
from viewer.viewport import ViewportWidget
from viewer.panels.hierarchy_panel import HierarchyPanel
from viewer.panels.layer_panel import LayerPanel
from viewer.panels.property_panel import PropertyPanel
from viewer.panels.statistics_panel import StatisticsPanel
from viewer.panels.console_panel import ConsolePanel


DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #12121f;
    color: #dddddd;
    font-family: -apple-system, "Helvetica Neue", "Segoe UI", system-ui, sans-serif;
    font-size: 12px;
}
QMenuBar {
    background: #1a1a2e;
    color: #dddddd;
    border-bottom: 1px solid #2a2a4a;
}
QMenuBar::item:selected { background: #2a2a4a; }
QMenu {
    background: #1a1a2e;
    color: #dddddd;
    border: 1px solid #2a2a4a;
}
QMenu::item:selected { background: #3a3a5c; }
QToolBar {
    background: #1a1a2e;
    border-bottom: 1px solid #2a2a4a;
    spacing: 4px;
    padding: 2px 6px;
}
QToolBar QToolButton {
    color: #dddddd;
    padding: 3px 10px;
    border-radius: 4px;
}
QToolBar QToolButton:hover  { background: #2a2a4a; }
QToolBar QToolButton:pressed { background: #3a3a5c; }
QDockWidget {
    background: #161625;
    color: #dddddd;
    titlebar-close-icon: url(none);
}
QDockWidget::title {
    background: #1a1a2e;
    padding: 4px 8px;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
    color: #aaaacc;
    border-bottom: 1px solid #2a2a4a;
}
QStatusBar { background: #0d0d1a; color: #777799; font-size: 10px; }
QScrollBar:vertical {
    background: #1a1a2e; width: 6px;
}
QScrollBar::handle:vertical { background: #3a3a5c; border-radius: 3px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, project_dir: str | None = None):
        super().__init__()
        self.setWindowTitle("RebarFusion — Engineering Viewer")
        self.resize(1600, 960)
        self.setStyleSheet(DARK_STYLESHEET)

        # ── Scene ─────────────────────────────────────────────────────────
        self.scene = SceneManager()

        # ── Viewport ──────────────────────────────────────────────────────
        self.viewport = ViewportWidget(self.scene, self)
        self.setCentralWidget(self.viewport)

        # ── Panels ────────────────────────────────────────────────────────
        self._hier_panel  = HierarchyPanel(self.scene)
        self._stats_panel = StatisticsPanel(self.scene)
        self._layer_panel = LayerPanel(self.scene)
        self._prop_panel  = PropertyPanel(self.scene)
        self._console     = ConsolePanel(self.scene)

        # Left dock
        left_dock = QDockWidget("HIERARCHY", self)
        left_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        left_widget = QWidget()
        lv = QVBoxLayout(left_widget)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        lv.addWidget(self._hier_panel)
        lv.addWidget(QLabel())  # separator
        lv.addWidget(self._stats_panel)
        left_dock.setWidget(left_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left_dock)

        # Right dock
        right_dock = QDockWidget("PROPERTIES", self)
        right_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        right_widget = QWidget()
        rv = QVBoxLayout(right_widget)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addWidget(self._layer_panel)
        rv.addWidget(QLabel())
        rv.addWidget(self._prop_panel)
        right_dock.setWidget(right_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, right_dock)

        # Bottom dock
        bottom_dock = QDockWidget("CONSOLE", self)
        bottom_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        bottom_dock.setWidget(self._console)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, bottom_dock)

        # ── Menu Bar ──────────────────────────────────────────────────────
        self._build_menu()

        # ── Toolbar ───────────────────────────────────────────────────────
        self._build_toolbar()

        # ── Status bar ────────────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

        # Connect scene for status updates
        self.scene.on_data_loaded(self._on_data_loaded)

        # ── Auto-load ─────────────────────────────────────────────────────
        if project_dir:
            QTimer.singleShot(300, lambda: self._load_project(project_dir))

    # ─── Menu ─────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("File")
        open_act = QAction("Open Project…", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_project_dialog)
        file_menu.addAction(open_act)
        file_menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(QApplication.quit)
        file_menu.addAction(quit_act)

        # View
        view_menu = mb.addMenu("View")
        for name, fn in self.viewport.camera_presets.items():
            a = QAction(name, self)
            a.triggered.connect(fn)
            view_menu.addAction(a)

        # Debug
        debug_menu = mb.addMenu("Debug")
        fit_act = QAction("Fit All", self)
        fit_act.triggered.connect(self.viewport.fit_view)
        debug_menu.addAction(fit_act)

    # ─── Toolbar ──────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = QToolBar("Camera")
        tb.setMovable(False)
        self.addToolBar(tb)

        open_btn = QAction("📂 Open Project", self)
        open_btn.triggered.connect(self._open_project_dialog)
        tb.addAction(open_btn)

        tb.addSeparator()

        for name, fn in self.viewport.camera_presets.items():
            a = QAction(name, self)
            a.triggered.connect(fn)
            tb.addAction(a)

        tb.addSeparator()

        fit_a = QAction("⊡ Fit All", self)
        fit_a.triggered.connect(self.viewport.fit_view)
        tb.addAction(fit_a)

    # ─── Project loading ──────────────────────────────────────────────────────

    def _open_project_dialog(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Project Directory", os.path.expanduser("~")
        )
        if directory:
            self._load_project(directory)

    def _load_project(self, directory: str):
        self.status.showMessage(f"Loading {directory}…")
        # Run pipeline in-thread (for large projects, move to QThread)
        try:
            from core.project import DrawingProject
            from core.readers.dxf_reader import DXFReader
            from core.geometry.canonicalizer import canonicalize
            from core.spatial.engine import SpatialQueryEngine
            from core.topology.node_builder import build_nodes
            from core.topology.builder import TopologyBuilder
            from core.recognition.registry import RecognizerRegistry, RecognitionCache
            from core.recognition.recognizers import (
                StraightBarRecognizer, LBarRecognizer, UBarRecognizer, StirrupRecognizer,
                BranchRecognizer, DimensionRecognizer, LeaderRecognizer,
                StructuralOutlineRecognizer
            )
            import uuid
            from core.recognition.annotations import Annotation, AnnotationParser
            from core.engineering.association import EngineeringAssociationEngine
            from core.engineering.solver import ConstraintSolver
            project = DrawingProject()
            manifest = project.load_directory(directory)
            reader = DXFReader()

            canon_repo = None
            node_repo = None
            graph = None
            comp_repo = None
            recognition_cache = None

            registry = RecognizerRegistry()
            registry.register(StraightBarRecognizer())
            registry.register(LBarRecognizer())
            registry.register(UBarRecognizer())
            registry.register(StirrupRecognizer())
            registry.register(BranchRecognizer())
            registry.register(StructuralOutlineRecognizer())
            registry.register(DimensionRecognizer())
            registry.register(LeaderRecognizer())

            # Load first supported drawing (extendable to multi-drawing overlay)
            for filename, drawing in manifest.drawings.items():
                if drawing.duplicate_of or not drawing.capabilities.geometry:
                    continue
                phase2 = reader.read_geometry(drawing.filepath, drawing.identity)
                canon_repo, _ = canonicalize(phase2, drawing.filepath)
                engine = SpatialQueryEngine.build(canon_repo)
                node_repo, _, _ = build_nodes(canon_repo, engine, filename)
                builder = TopologyBuilder(node_repo, canon_repo)
                graph, comp_repo, metrics, _ = builder.build()
                
                recognition_cache = RecognitionCache()
                for comp in comp_repo.components.values():
                    result = registry.evaluate(comp, graph)
                    recognition_cache.set(comp.id, result)
                    
                # Phase 8 Solver
                annotations = []
                for t in canon_repo.texts:
                    annotations.append(Annotation(uuid.uuid4(), 'TEXT', t.text, t.insertion_point, t.bounding_box, t.rotation, t.layer, t.id))
                for t in canon_repo.mtexts:
                    annotations.append(Annotation(uuid.uuid4(), 'MTEXT', t.text, t.insertion_point, t.bounding_box, t.rotation, t.layer, t.id))
                for d in canon_repo.dimensions:
                    annotations.append(Annotation(uuid.uuid4(), 'DIMENSION', d.text, d.defpoint, d.bounding_box, 0.0, d.layer, d.id, d.measurement, d.p1, d.p2))
                
                leaders = []
                import ezdxf
                doc = ezdxf.readfile(drawing.filepath)
                msp = doc.modelspace()
                for e in msp:
                    if e.dxftype() == 'LINE' and e.dxf.layer == 'G-ANNO-TEXT':
                        leaders.append(((e.dxf.start.x, e.dxf.start.y, e.dxf.start.z), (e.dxf.end.x, e.dxf.end.y, e.dxf.end.z)))
                        
                assoc_engine = EngineeringAssociationEngine(graph, comp_repo, engine, recognition_cache)
                anno_parser = AnnotationParser()
                groups = assoc_engine.cluster_annotations(annotations, anno_parser, leaders)
                
                solver = ConstraintSolver()
                for group in groups:
                    if not group.tokens:
                        continue
                    candidates = assoc_engine.find_group_candidates(group, k=5)
                    if candidates:
                        constraints = assoc_engine.build_constraints(candidates)
                        for c in constraints:
                            solver.add_constraint(c)
                eng_objects = solver.solve()

                self._console.log(f"Loaded: {filename}")
                self._console.log(f"  Nodes={metrics['total_nodes']}  Edges={metrics['total_edges']}  Components={metrics['connected_components']}")
                break  # TODO: multi-drawing mode

            self.scene.recognition_cache = recognition_cache
            self.scene.engineering_objects = eng_objects
            self.scene.load(
                manifest=manifest,
                canon_repo=canon_repo,
                node_repo=node_repo,
                graph=graph,
                comp_repo=comp_repo,
            )
            self.status.showMessage(f"Loaded: {directory}")
            self.viewport.fit_view()

        except Exception as e:
            self.status.showMessage(f"Error: {e}")
            self._console.log(f"[ERROR] {e}")
            import traceback
            self._console.log(traceback.format_exc())

    def _on_data_loaded(self):
        self.status.showMessage("Project loaded. Rendering…")


def launch(project_dir: str | None = None):
    """Entry point."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("RebarFusion Engineering Viewer")
    window = MainWindow(project_dir=project_dir)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", default=None)
    args = parser.parse_args()
    launch(args.directory)
