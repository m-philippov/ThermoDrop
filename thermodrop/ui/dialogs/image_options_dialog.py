"""Диалог параметров экспортируемого изображения: размер, заголовок, подписи осей."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Optional, Sequence, Tuple

from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from thermodrop.rendering.labels import AxisLabels
from thermodrop.services.export_service import ImageOptions
from thermodrop.ui.widgets.common import int_spin

#: (поле AxisLabels, подпись в диалоге, текст по умолчанию)
LabelField = Tuple[str, str, str]


class ImageOptionsDialog(QDialog):
    def __init__(self, title: str, defaults: ImageOptions, label_fields: Sequence[LabelField] = (),
                 show_axes: Optional[bool] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._defaults = defaults

        self._width = int_spin(100, 10000, 10)
        self._height = int_spin(100, 10000, 10)
        self._dpi = int_spin(50, 1200, 25)
        self._transparent = QCheckBox("Прозрачный фон")
        self._title = QLineEdit()
        self._title.setPlaceholderText("необязательно")
        self._width.setValue(defaults.width_px)
        self._height.setValue(defaults.height_px)
        self._dpi.setValue(defaults.dpi)
        self._transparent.setChecked(defaults.transparent)
        self._title.setText(defaults.title)

        size_box = QGroupBox("Изображение")
        form = QFormLayout(size_box)
        form.addRow("Ширина, пикс.:", self._width)
        form.addRow("Высота, пикс.:", self._height)
        form.addRow("Разрешение, dpi:", self._dpi)
        form.addRow("Заголовок:", self._title)
        form.addRow(self._transparent)

        layout = QVBoxLayout(self)
        layout.addWidget(size_box)

        self._label_edits: Dict[str, QLineEdit] = {}
        self._label_defaults: Dict[str, str] = {}
        self._show_axes: Optional[QCheckBox] = None
        if label_fields:
            labels_box = QGroupBox("Подписи осей")
            labels_form = QFormLayout(labels_box)
            if show_axes is not None:
                self._show_axes = QCheckBox("Показывать оси")
                self._show_axes.setChecked(show_axes)
                labels_form.addRow(self._show_axes)
            for attr, caption, default in label_fields:
                edit = QLineEdit()
                custom = getattr(defaults.labels, attr)
                edit.setText(default if custom is None else custom)
                edit.setPlaceholderText("пусто — без подписи")
                self._label_edits[attr] = edit
                self._label_defaults[attr] = default
                labels_form.addRow(caption, edit)
            layout.addWidget(labels_box)
            if self._show_axes is not None:
                self._show_axes.toggled.connect(self._update_enabled)
                self._update_enabled()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_enabled(self) -> None:
        # Подписи X/Y/Z видны только при включённых осях; подпись шкалы — всегда.
        on = self._show_axes.isChecked()
        for attr, edit in self._label_edits.items():
            if attr != "colorbar":
                edit.setEnabled(on)

    def options(self) -> ImageOptions:
        # Неизменённая подпись остаётся «по умолчанию», чтобы следовать за режимом T/ΔT.
        labels = replace(AxisLabels(), **{
            a: (None if e.text() == self._label_defaults[a] else e.text())
            for a, e in self._label_edits.items()})
        return ImageOptions(width_px=self._width.value(), height_px=self._height.value(),
                            dpi=self._dpi.value(), transparent=self._transparent.isChecked(),
                            title=self._title.text().strip(), labels=labels,
                            show_axes=self._show_axes.isChecked() if self._show_axes else None)
