from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QHBoxLayout, QSlider, QWidget

from viewer.scene import SceneManager


class TimelinePanel(QWidget):
    def __init__(self, scene: SceneManager, parent=None):
        super().__init__(parent)
        self.scene = scene

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self._label = QLabel()
        self._label.setStyleSheet("color:#dddddd; font-weight:bold;")
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(len(SceneManager.STAGES) - 1)
        self._slider.setValue(len(SceneManager.STAGES) - 1)
        self._slider.valueChanged.connect(self._on_value)

        layout.addWidget(QLabel("Timeline"))
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._label)
        self.setLayout(layout)

        scene.on_stage_changed(self._on_stage_changed)
        self._on_stage_changed(scene.current_stage)

    def _on_value(self, value: int):
        self.scene.set_stage(SceneManager.STAGES[value])

    def _on_stage_changed(self, stage: str):
        self._label.setText(stage)
        index = SceneManager.STAGES.index(stage)
        if self._slider.value() != index:
            self._slider.blockSignals(True)
            self._slider.setValue(index)
            self._slider.blockSignals(False)
