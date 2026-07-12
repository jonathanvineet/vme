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
    QToolBar, QStatusBar, QWidget, QVBoxLayout, QLabel, QFileDialog,
    QSplitter, QLineEdit
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon

from viewer.scene import SceneManager
from viewer.viewport import ViewportWidget
from viewer.viewport2d import Viewport2D
from viewer.project_tree import ProjectTreePanel
from viewer.panels.layer_panel import LayerPanel
from viewer.panels.property_panel import PropertyPanel
from viewer.panels.statistics_panel import StatisticsPanel
from viewer.panels.console_panel import ConsolePanel
from viewer.panels.timeline_panel import TimelinePanel
from viewer.controllers.project_controller import ProjectController
from viewer.workbench_project import WorkbenchProject


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


class _HeadlessViewportPlaceholder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        label = QLabel("3D viewport unavailable in headless mode")
        label.setStyleSheet("color:#8888aa; font-size:14px;")
        layout.addWidget(label)
        layout.addStretch()
        self.camera_presets = {
            "Top": lambda: None,
            "Front": lambda: None,
            "Left": lambda: None,
            "Isometric": lambda: None,
            "Fit": lambda: None,
        }

    def fit_view(self):
        return None


class MainWindow(QMainWindow):
    def __init__(self, project_dir: str | None = None):
        super().__init__()
        self.setWindowTitle("RebarFusion — Engineering Viewer")
        self.resize(1600, 960)
        self.setStyleSheet(DARK_STYLESHEET)

        # ── Scene & Controllers ───────────────────────────────────────────
        self.scene = SceneManager()
        self.project_controller = ProjectController(self)
        self.project_controller.project_loaded.connect(self._on_project_loaded)
        self.project_controller.project_load_failed.connect(self._on_project_load_failed)
        self.project_controller.status_message.connect(self.statusBar().showMessage)
        self.project_controller.log_message.connect(self._on_log_message)


        # ── Workbench Viewports ───────────────────────────────────────────
        self.viewport2d = Viewport2D(self.scene, self)
        if os.environ.get("QT_QPA_PLATFORM", "").lower() in {"offscreen", "minimal"}:
            self.viewport = _HeadlessViewportPlaceholder(self)
        else:
            try:
                self.viewport = ViewportWidget(self.scene, self)
            except Exception:
                self.viewport = _HeadlessViewportPlaceholder(self)
        center_split = QSplitter(Qt.Orientation.Vertical)
        center_split.addWidget(self.viewport2d)
        center_split.addWidget(self.viewport)
        center_split.setSizes([560, 360])
        self.setCentralWidget(center_split)

        # ── Panels ────────────────────────────────────────────────────────
        self._tree_panel  = ProjectTreePanel(self.scene)
        self._stats_panel = StatisticsPanel(self.scene)
        self._layer_panel = LayerPanel(self.scene)
        self._prop_panel  = PropertyPanel(self.scene)
        self._console     = ConsolePanel(self.scene)
        self._timeline    = TimelinePanel(self.scene)

        # Left dock
        left_dock = QDockWidget("HIERARCHY", self)
        left_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        left_widget = QWidget()
        lv = QVBoxLayout(left_widget)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        lv.addWidget(self._tree_panel)
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

        timeline_dock = QDockWidget("TIMELINE", self)
        timeline_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        timeline_dock.setWidget(self._timeline)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, timeline_dock)

        # ── Menu Bar ──────────────────────────────────────────────────────
        self._build_menu()

        # ── Toolbar ───────────────────────────────────────────────────────
        self._build_toolbar()

        # ── Status bar ────────────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

        # Connect scene for status updates
        self.scene.on_data_loaded(self._on_scene_data_loaded)

        # ── Auto-load ─────────────────────────────────────────────────────
        if project_dir:
            QTimer.singleShot(300, lambda: self.project_controller.load_project(project_dir))

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

        debug_menu.addSeparator()

        explode_act = QAction("Exploded View", self)
        explode_act.setCheckable(True)
        explode_act.toggled.connect(self.scene.set_debug_exploded_view)
        debug_menu.addAction(explode_act)

        z_scale_act = QAction("Z Exaggeration x30", self)
        z_scale_act.setCheckable(True)
        z_scale_act.toggled.connect(lambda checked: self.scene.set_debug_z_scale(30.0 if checked else 1.0))
        debug_menu.addAction(z_scale_act)

        reset_debug_act = QAction("Reset Debug View", self)
        reset_debug_act.triggered.connect(lambda: self._reset_debug_view(explode_act, z_scale_act))
        debug_menu.addAction(reset_debug_act)

    def _reset_debug_view(self, explode_act: QAction, z_scale_act: QAction):
        self.scene.reset_debug_view()
        explode_act.setChecked(False)
        z_scale_act.setChecked(False)


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

        tb.addSeparator()
        tb.addWidget(QLabel("Search:"))
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search mark, assembly, bar...")
        self._search_box.setMinimumWidth(260)
        self._search_box.returnPressed.connect(lambda: self._search(self._search_box.text()))
        tb.addWidget(self._search_box)

        tb.addSeparator()
        explode_btn = QAction("Explode", self)
        explode_btn.setCheckable(True)
        explode_btn.toggled.connect(self.scene.set_debug_exploded_view)
        tb.addAction(explode_btn)

        z_btn = QAction("Z x30", self)
        z_btn.setCheckable(True)
        z_btn.toggled.connect(lambda checked: self.scene.set_debug_z_scale(30.0 if checked else 1.0))
        tb.addAction(z_btn)

    def _search(self, query: str):
        if self.scene.search(query):
            self.status.showMessage(f"Selected: {query}")
        else:
            self.status.showMessage(f"No match: {query}")

    def _reset_debug_view(self, explode_act: QAction, z_scale_act: QAction):
        self.scene.reset_debug_view()
        explode_act.blockSignals(True)
        z_scale_act.blockSignals(True)
        try:
            explode_act.setChecked(False)
            z_scale_act.setChecked(False)
        finally:
            explode_act.blockSignals(False)
            z_scale_act.blockSignals(False)

    def _open_project_dialog(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Project Directory", os.path.expanduser("~")
        )
        if directory:
            self.project_controller.load_project(directory)

    # ─── Project Loading Handlers ─────────────────────────────────────────────

    def _on_project_loaded(self, project: WorkbenchProject):
        """Handle successful project loading."""
        self.scene.load_project(project)
        self.viewport.fit_view()

    def _on_project_load_failed(self, error_message: str):
        """Handle failed project loading."""
        # The controller already logs the detailed error.
        # We could show a dialog box here if needed.
        pass

    def _on_log_message(self, message: str):
        """Display a message from a controller in the console."""
        self._console.log(message)

    def _on_scene_data_loaded(self):
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
