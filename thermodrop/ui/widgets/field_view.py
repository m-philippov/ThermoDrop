"""Окно 1: температурное поле кадра и эллипс выделения."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from thermodrop.core.models import EllipseRegion, ReferenceMode, RegionData, ThermalField, ValueMode
from thermodrop.rendering.colormaps import COLORMAPS, DEFAULT_COLORMAP, lookup_table
from thermodrop.services.session import AnalysisSession
from thermodrop.ui.widgets.common import double_spin, enum_combo, select_data, signals_blocked
from thermodrop.ui.widgets.ellipse_selector import EllipseSelector

log = logging.getLogger(__name__)


def make_pg_colormap(name: str) -> pg.ColorMap:
    lut = lookup_table(name)
    return pg.ColorMap(pos=np.linspace(0.0, 1.0, len(lut)), color=lut)


class FieldView(QWidget):
    def __init__(self, session: AnalysisSession, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._session = session
        self._field: Optional[ThermalField] = None
        self._syncing = False

        self._build_plot()
        self._build_controls()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._plot, 1)
        layout.addWidget(self._controls)

        session.field_changed.connect(self._on_field_changed)
        session.region_changed.connect(self._on_region_changed)
        session.region_data_changed.connect(self._on_region_data_changed)
        self.setEnabled(False)

    # ------------------------------------------------------------------ построение

    def _build_plot(self) -> None:
        self._plot = pg.PlotWidget()
        self._plot.setBackground("w")
        item = self._plot.getPlotItem()
        item.invertY(True)
        item.setAspectLocked(True)
        item.setLabel("bottom", "Столбец, пикс.")
        item.setLabel("left", "Строка, пикс.")
        item.showGrid(False, False)

        self._image = pg.ImageItem()
        item.addItem(self._image)
        self._cbar = pg.ColorBarItem(values=(0.0, 1.0), colorMap=make_pg_colormap(DEFAULT_COLORMAP),
                                     interactive=True, width=14, label="T, °C")
        self._cbar.setImageItem(self._image, insert_in=item)
        self._cbar.sigLevelsChangeFinished.connect(self._on_levels_changed)

        self._selector = EllipseSelector()
        self._selector.setVisible(False)
        item.addItem(self._selector)
        self._selector.signals.region_edited.connect(self._on_selector_edited)

        self._plot.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self._plot.setToolTip("✥ в центре — перемещение эллипса, ⟳ на краю — поворот,\n"
                              "сам эллипс — изменение размера (с Shift — пропорционально).\n"
                              "Колесо — масштаб изображения; ПКМ — меню вида.\n"
                              "Шкалу справа можно тянуть мышью.")

    def _build_controls(self) -> None:
        self._controls = QWidget()
        grid = QGridLayout(self._controls)
        grid.setContentsMargins(0, 0, 0, 0)

        # Эллипс
        box = QGroupBox("Эллипс")
        form = QGridLayout(box)
        self._cx = double_spin(-1e4, 1e4, 0.5, 1, tooltip="Центр X (столбец)")
        self._cy = double_spin(-1e4, 1e4, 0.5, 1, tooltip="Центр Y (строка)")
        self._rx = double_spin(0.5, 1e4, 0.5, 1, tooltip="Полуось вдоль X (до поворота)")
        self._ry = double_spin(0.5, 1e4, 0.5, 1, tooltip="Полуось вдоль Y (до поворота)")
        self._angle = double_spin(-180, 180, 1, 1, "°", "Угол поворота")
        self._angle.setWrapping(True)
        for col, (label, spin) in enumerate((("X", self._cx), ("Y", self._cy), ("Rx", self._rx),
                                             ("Ry", self._ry), ("∠", self._angle))):
            form.addWidget(QLabel(label), 0, 2 * col, Qt.AlignRight)
            form.addWidget(spin, 0, 2 * col + 1)
            spin.valueChanged.connect(self._on_spin_changed)
        self._detect_btn = QPushButton("Найти каплю")
        self._detect_btn.setToolTip("Автоматически поставить эллипс на каплю")
        self._detect_btn.clicked.connect(self._detect_region)
        self._center_btn = QPushButton("По центру")
        self._center_btn.clicked.connect(self._reset_region)
        form.addWidget(self._detect_btn, 1, 0, 1, 5)
        form.addWidget(self._center_btn, 1, 5, 1, 5)
        grid.addWidget(box, 0, 0, 1, 2)

        # Данные
        data_box = QGroupBox("Значения")
        data_form = QFormLayout(data_box)
        self._mode = enum_combo(ValueMode)
        self._mode.currentIndexChanged.connect(
            lambda _: self._session.set_value_mode(self._mode.currentData()))
        self._ref_mode = enum_combo(ReferenceMode)
        self._ref_mode.currentIndexChanged.connect(self._on_ref_mode_changed)
        self._ref_value = double_spin(-273, 3000, 0.1, 2, " °C", "Опорная температура (вручную)")
        self._ref_value.valueChanged.connect(self._session.set_manual_reference)
        self._ref_label = QLabel("—")
        ref_row = QHBoxLayout()
        ref_row.addWidget(self._ref_mode, 1)
        ref_row.addWidget(self._ref_value)
        data_form.addRow("Режим:", self._mode)
        data_form.addRow("Tоп:", ref_row)
        data_form.addRow("Tоп =", self._ref_label)
        grid.addWidget(data_box, 1, 0)

        view_box = QGroupBox("Изображение")
        view_form = QFormLayout(view_box)
        self._cmap = QComboBox()
        self._cmap.addItems(COLORMAPS)
        self._cmap.setCurrentText(DEFAULT_COLORMAP)
        self._cmap.currentTextChanged.connect(self._on_cmap_changed)
        orient = QHBoxLayout()
        self._transpose_btn = QPushButton("Транспонировать")
        self._transpose_btn.clicked.connect(self._session.transpose)
        self._rotate_btn = QPushButton("Повернуть 90°")
        self._rotate_btn.clicked.connect(self._session.rotate90)
        self._autolevels_btn = QPushButton("Авто шкала")
        self._autolevels_btn.clicked.connect(self._auto_levels)
        orient.addWidget(self._transpose_btn)
        orient.addWidget(self._rotate_btn)
        view_form.addRow("Палитра:", self._cmap)
        view_form.addRow(orient)
        view_form.addRow(self._autolevels_btn)
        grid.addWidget(view_box, 1, 1)

        self._hover = QLabel(" ")
        self._hover.setStyleSheet("color: #555;")
        grid.addWidget(self._hover, 2, 0, 1, 2)

        select_data(self._mode, self._session.value_mode)
        select_data(self._ref_mode, self._session.reference_mode)
        self._ref_value.setValue(self._session.manual_reference)
        self._ref_value.setEnabled(self._session.reference_mode is ReferenceMode.MANUAL)

    # ------------------------------------------------------------------ реакции на сессию

    def _on_field_changed(self, field: ThermalField) -> None:
        self._field = field
        self.setEnabled(True)
        self._image.setImage(field.data, autoLevels=False)
        self._auto_levels(log_action=False)
        self._plot.getPlotItem().getViewBox().autoRange(padding=0.02)
        for spin in (self._cx, self._rx):
            spin.setMaximum(field.cols * 2)
        for spin in (self._cy, self._ry):
            spin.setMaximum(field.rows * 2)

    def _on_region_changed(self, region: EllipseRegion) -> None:
        self._syncing = True
        try:
            self._selector.set_region(region)
            self._selector.setVisible(True)
            spins = (self._cx, self._cy, self._rx, self._ry, self._angle)
            with signals_blocked(*spins):
                self._cx.setValue(region.cx)
                self._cy.setValue(region.cy)
                self._rx.setValue(region.rx)
                self._ry.setValue(region.ry)
                self._angle.setValue(region.angle_deg)
        finally:
            self._syncing = False

    def _on_region_data_changed(self, data: RegionData) -> None:
        select_data(self._mode, self._session.value_mode)
        self._ref_label.setText("%.2f °C (пикселей в эллипсе: %d)" % (data.reference, int(data.mask.sum())))

    # ------------------------------------------------------------------ действия пользователя

    def _on_selector_edited(self, region: EllipseRegion, final: bool) -> None:
        if self._syncing or self._field is None:
            return
        self._session.set_region(region, final=final)

    def _on_spin_changed(self, _value: float) -> None:
        if self._syncing or self._field is None:
            return
        try:
            region = EllipseRegion(self._cx.value(), self._cy.value(), self._rx.value(),
                                   self._ry.value(), self._angle.value())
        except ValueError as exc:
            log.warning("Некорректные параметры эллипса: %s", exc)
            return
        self._session.set_region(region, final=True)

    def _detect_region(self) -> None:
        if self._field is not None and not self._session.detect_region():
            QMessageBox.information(self, "Автопоиск", "Каплю найти не удалось — выделите область вручную.")

    def _reset_region(self) -> None:
        if self._field is None:
            return
        log.info("Эллипс сброшен в центр кадра")
        self._session.set_region(EllipseRegion.centered_in(self._field.rows, self._field.cols))

    def _on_ref_mode_changed(self, _index: int) -> None:
        mode = self._ref_mode.currentData()
        self._ref_value.setEnabled(mode is ReferenceMode.MANUAL)
        if mode is ReferenceMode.MANUAL and self._session.region_data is not None:
            with signals_blocked(self._ref_value):
                self._ref_value.setValue(self._session.region_data.reference)
            self._session.set_manual_reference(self._session.region_data.reference)
        self._session.set_reference_mode(mode)

    def _on_cmap_changed(self, name: str) -> None:
        log.info("Палитра изображения: %s", name)
        self._cbar.setColorMap(make_pg_colormap(name))

    def _auto_levels(self, log_action: bool = True) -> None:
        if self._field is None:
            return
        data = self._field.data
        lo, hi = float(np.nanmin(data)), float(np.nanmax(data))
        if hi <= lo:
            hi = lo + 1.0
        self._cbar.setLevels((lo, hi))
        if log_action:
            log.info("Шкала изображения: авто %.2f…%.2f °C", lo, hi)

    def _on_levels_changed(self, cbar) -> None:
        lo, hi = cbar.levels()
        log.info("Шкала изображения: %.2f…%.2f °C", lo, hi)

    def _on_mouse_moved(self, scene_pos) -> None:
        if self._field is None:
            return
        point = self._plot.getPlotItem().getViewBox().mapSceneToView(scene_pos)
        col, row = int(np.floor(point.x())), int(np.floor(point.y()))
        if 0 <= row < self._field.rows and 0 <= col < self._field.cols:
            t = self._field.data[row, col]
            text = "строка %d, столбец %d: T = %.2f °C" % (row, col, t)
            if self._session.region_data is not None:
                text += ", ΔT = %.2f °C" % (t - self._session.reference)
            self._hover.setText(text)
        else:
            self._hover.setText(" ")
