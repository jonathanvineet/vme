"""
viewer/panels/layer_panel.py

Layer visibility panel — checkbox list of all registered layers.
Toggles SceneManager.set_layer_visible() on check/uncheck.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox
from PySide6.QtCore import Qt

from viewer.scene import SceneManager


class LayerPanel(QWidget):
    def __init__(self, scene: SceneManager, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.setMinimumWidth(180)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)

        header = QLabel("LAYERS")
        header.setStyleSheet("font-weight:bold; color:#aaaaaa; font-size:10px; letter-spacing:1px;")
        layout.addWidget(header)

        self._checkboxes = {}
        for name, state in scene.layers.items():
            cb = QCheckBox(name)
            cb.setChecked(state.visible)
            cb.setStyleSheet("color:#dddddd; font-size:11px;")
            cb.checkStateChanged.connect(lambda s, n=name: self.scene.set_layer_visible(n, s == Qt.CheckState.Checked))
            layout.addWidget(cb)
            self._checkboxes[name] = cb

        family_header = QLabel("FAMILIES")
        family_header.setStyleSheet("font-weight:bold; color:#aaaaaa; font-size:10px; letter-spacing:1px; margin-top:8px;")
        layout.addWidget(family_header)

        family_options = [
            ("Representative", "representative", scene.show_family_representative),
            ("Expanded", "expanded", scene.show_family_expanded),
            ("Missing Members", "missing", scene.show_family_missing),
            ("QA", "qa", scene.show_family_qa),
        ]
        for label, key, checked in family_options:
            cb = QCheckBox(label)
            cb.setChecked(checked)
            cb.setStyleSheet("color:#dddddd; font-size:11px;")
            cb.checkStateChanged.connect(lambda s, k=key: self.scene.set_family_display_option(k, s == Qt.CheckState.Checked))
            layout.addWidget(cb)

        layout.addStretch()
        self.setLayout(layout)
