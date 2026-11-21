"""Окно 2: трёхмерная столбчатая диаграмма выделенной области.

Мышь: ЛКМ — вращение, СКМ — сдвиг, колесо или щипок тачпада — масштаб,
Shift+колесо — верхняя граница шкалы, Ctrl+Shift+колесо — нижняя.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from thermodrop.core.models import RegionData
from thermodrop.rendering.bar3d import Bar3DInfo, Bar3DRenderer, Bar3DStyle, ZDirection
from thermodrop.rendering.colormaps import COLORMAPS
from thermodrop.services.session import AnalysisSession
from thermodrop.ui.widgets.common import Debouncer, double_spin, enum_combo, int_spin, select_data, signals_blocked

log = logging.getLogger(__name__)

MATLAB_VIEW = (30.0, -37.5)
TOP_VIEW = (90.0, -90.0)


class Bar3DView(QWidget):
    export_requested = pyqtSignal()

    def __init__(self, session: AnalysisSession, renderer: Bar3DRenderer,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._session = session
        self._renderer = renderer
        self._style = Bar3DStyle()
        self._info: Optional[Bar3DInfo] = None
        self._ax = None
        self._data: Optional[RegionData] = None

        self._figure = Figure(figsize=(5, 4), dpi=100)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._canvas.setFocusPolicy(Qt.ClickFocus)
        self._canvas.setToolTip(__doc__.split("\n\n", 1)[1].strip())
        self._canvas.mpl_connect("scroll_event", self._on_scroll)
        self._canvas.mpl_connect("button_release_event", self._on_release)

        self._redraw = Debouncer(200, self._render, self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._canvas, 1)
        layout.addWidget(self._build_panel())

        session.region_data_changed.connect(self._on_region_data)
        session.histogram_changed.connect(self._on_threshold_maybe_changed)
        self._apply_style_to_controls()
        self._render()

    @property
    def style(self) -> Bar3DStyle:
        return self._style

    # ------------------------------------------------------------------ панель

    def _build_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)

        scale = QGroupBox("Шкала")
        f = QFormLayout(scale)
        self._auto = QCheckBox("Авто")
        self._auto.toggled.connect(lambda on: self._update(auto_scale=on))
        self._vmin = double_spin(-1e4, 1e4, 0.1, 2, tooltip="Нижняя граница (Ctrl+Shift+колесо)")
        self._vmax = double_spin(-1e4, 1e4, 0.1, 2, tooltip="Верхняя граница (Shift+колесо)")
        self._vmin.valueChanged.connect(lambda v: self._update(vmin=v, auto_scale=False))
        self._vmax.valueChanged.connect(lambda v: self._update(vmax=v, auto_scale=False))
        self._cmap = QComboBox()
        self._cmap.addItems(COLORMAPS)
        self._cmap.currentTextChanged.connect(lambda name: self._update(cmap=name))
        f.addRow(self._auto)
        f.addRow("Мин:", self._vmin)
        f.addRow("Макс:", self._vmax)
        f.addRow("Палитра:", self._cmap)

        view = QGroupBox("Вид")
        f = QFormLayout(view)
        self._elev = double_spin(-180, 180, 5, 1, "°", "Угол возвышения")
        self._azim = double_spin(-360, 360, 5, 1, "°", "Азимут")
        self._roll = double_spin(-180, 180, 5, 1, "°", "Крен")
        self._zoom = double_spin(0.1, 10, 0.1, 2, "×", "Масштаб (колесо мыши)")
        self._zasp = double_spin(0.02, 10, 0.05, 2, tooltip="Высота столбцов относительно основания")
        self._elev.valueChanged.connect(lambda v: self._update(elev=v))
        self._azim.valueChanged.connect(lambda v: self._update(azim=v))
        self._roll.valueChanged.connect(lambda v: self._update(roll=v))
        self._zoom.valueChanged.connect(lambda v: self._update(zoom=v))
        self._zasp.valueChanged.connect(lambda v: self._update(z_aspect=v))
        presets = QHBoxLayout()
        for title, (elev, azim) in (("MATLAB", MATLAB_VIEW), ("Сверху", TOP_VIEW)):
            btn = QPushButton(title)
            btn.clicked.connect(lambda _=False, e=elev, a=azim: self._update(elev=e, azim=a, roll=0.0))
            presets.addWidget(btn)
        f.addRow("Возвыш.:", self._elev)
        f.addRow("Азимут:", self._azim)
        f.addRow("Крен:", self._roll)
        f.addRow("Масштаб:", self._zoom)
        f.addRow("Высота:", self._zasp)
        f.addRow(presets)

        bars = QGroupBox("Столбцы")
        f = QFormLayout(bars)
        self._width = double_spin(0.05, 1.0, 0.05, 2, tooltip="Ширина столбца (доля клетки)")
        self._width.valueChanged.connect(lambda v: self._update(bar_width=v))
        self._block = int_spin(0, 50, tooltip="Укрупнение сетки: N×N пикселей в столбце (0 — авто)",
                               special="авто")
        self._block.valueChanged.connect(lambda v: self._update(block=v))
        self._gradient = QCheckBox("Градиент")
        self._gradient.toggled.connect(lambda on: self._update(gradient=on))
        self._segments = int_spin(1, 30, tooltip="Число сегментов градиента по высоте")
        self._segments.valueChanged.connect(lambda v: self._update(segments=v))
        grad_row = QHBoxLayout()
        grad_row.addWidget(self._gradient)
        grad_row.addWidget(self._segments)
        self._direction = enum_combo(ZDirection)
        self._direction.currentIndexChanged.connect(
            lambda _: self._update(z_direction=self._direction.currentData()))
        self._edges = QCheckBox("Рёбра")
        self._edges.toggled.connect(lambda on: self._update(show_edges=on))
        self._base = QCheckBox("Подложка")
        self._base.setToolTip("Плоские клетки вне эллипса")
        self._base.toggled.connect(lambda on: self._update(show_base=on))
        self._hide = QCheckBox("Скрыть ниже порога")
        self._hide.setToolTip("Порог задаётся линией на гистограмме")
        self._hide.toggled.connect(lambda on: self._update(hide_below_threshold=on))
        flags = QHBoxLayout()
        flags.addWidget(self._edges)
        flags.addWidget(self._base)
        f.addRow("Ширина:", self._width)
        f.addRow("Укрупн.:", self._block)
        f.addRow(grad_row)
        f.addRow("Ось Z:", self._direction)
        f.addRow(flags)
        f.addRow(self._hide)

        deco = QGroupBox("Оформление")
        f = QFormLayout(deco)
        self._axes = QCheckBox("Оси")
        self._axes.toggled.connect(lambda on: self._update(show_axes=on))
        self._colorbar = QCheckBox("Шкала")
        self._colorbar.toggled.connect(lambda on: self._update(show_colorbar=on))
        row = QHBoxLayout()
        row.addWidget(self._axes)
        row.addWidget(self._colorbar)
        f.addRow(row)

        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: #555;")
        export = QPushButton("Экспорт изображения…")
        export.clicked.connect(self.export_requested.emit)

        for w in (scale, view, bars, deco):
            v.addWidget(w)
        v.addWidget(self._info_label)
        v.addWidget(export)
        v.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(235)
        scroll.setMaximumWidth(270)
        return scroll

    def _apply_style_to_controls(self) -> None:
        s = self._style
        widgets = (self._auto, self._vmin, self._vmax, self._cmap, self._elev, self._azim, self._roll,
                   self._zoom, self._zasp, self._width, self._block, self._gradient, self._segments,
                   self._edges, self._base, self._hide, self._axes, self._colorbar)
        with signals_blocked(*widgets):
            self._auto.setChecked(s.auto_scale)
            self._vmin.setValue(s.vmin)
            self._vmax.setValue(s.vmax)
            self._cmap.setCurrentText(s.cmap)
            self._elev.setValue(s.elev)
            self._azim.setValue(s.azim)
            self._roll.setValue(s.roll)
            self._zoom.setValue(s.zoom)
            self._zasp.setValue(s.z_aspect)
            self._width.setValue(s.bar_width)
            self._block.setValue(s.block)
            self._gradient.setChecked(s.gradient)
            self._segments.setValue(s.segments)
            self._segments.setEnabled(s.gradient)
            self._edges.setChecked(s.show_edges)
            self._base.setChecked(s.show_base)
            self._hide.setChecked(s.hide_below_threshold)
            self._axes.setChecked(s.show_axes)
            self._colorbar.setChecked(s.show_colorbar)
        select_data(self._direction, s.z_direction)

    # ------------------------------------------------------------------ состояние

    _VIEW_ONLY = {"elev", "azim", "roll", "zoom"}

    def _update(self, **changes) -> None:
        changes = {k: v for k, v in changes.items() if getattr(self._style, k) != v}
        if not changes:
            return
        if changes.get("auto_scale") is False and self._info is not None:
            # Переход на ручную шкалу: фиксируем текущие границы.
            changes.setdefault("vmin", self._info.vmin)
            changes.setdefault("vmax", self._info.vmax)
        self._style = self._style.with_(**changes)
        log.info("3D: %s", ", ".join("%s=%s" % (k, _fmt(v)) for k, v in sorted(changes.items())))
        self._apply_style_to_controls()
        if set(changes) <= self._VIEW_ONLY and self._ax is not None:
            self._apply_view()
        else:
            self._redraw.trigger()

    def _on_region_data(self, data: RegionData) -> None:
        self._data = data
        self._redraw.trigger()

    def _on_threshold_maybe_changed(self) -> None:
        if self._style.hide_below_threshold:
            self._redraw.trigger()

    # ------------------------------------------------------------------ отрисовка

    def _render(self) -> None:
        self._info = self._renderer.render(self._figure, self._data, self._style, self._session.threshold)
        self._ax = self._figure.axes[0] if self._figure.axes and self._info else None
        if self._ax is not None:
            try:
                self._ax.mouse_init(rotate_btn=1, pan_btn=2, zoom_btn=[])
            except TypeError:
                pass
        self._canvas.draw_idle()
        if self._info is not None:
            if self._style.auto_scale:
                with signals_blocked(self._vmin, self._vmax):
                    self._vmin.setValue(self._info.vmin)
                    self._vmax.setValue(self._info.vmax)
            self._info_label.setText(
                "Клеток: %d, укрупнение %d×%d\nОснование: %.2f; шкала %.2f…%.2f%s" % (
                    self._info.cells, self._info.block, self._info.block, self._info.base,
                    self._info.vmin, self._info.vmax, "\nОсь Z инвертирована" if self._info.inverted else ""))
            log.debug("3D перерисован: %s", self._info)
        else:
            self._info_label.setText("")

    def _apply_view(self) -> None:
        s = self._style
        try:
            self._ax.view_init(elev=s.elev, azim=s.azim, roll=s.roll)
        except TypeError:
            self._ax.view_init(elev=s.elev, azim=s.azim)
        try:
            self._ax.set_box_aspect(self._info.box_aspect, zoom=s.zoom)
        except TypeError:  # matplotlib < 3.6
            pass
        self._canvas.draw_idle()

    # ------------------------------------------------------------------ мышь

    def _on_release(self, event) -> None:
        if self._ax is None or event.inaxes is not self._ax:
            return
        elev, azim = round(float(self._ax.elev), 1), round(float(self._ax.azim), 1)
        roll = round(float(getattr(self._ax, "roll", 0.0)), 1)
        if (elev, azim, roll) != (self._style.elev, self._style.azim, self._style.roll):
            self._update(elev=elev, azim=azim, roll=roll)

    def _on_scroll(self, event) -> None:
        if self._ax is None:
            return
        steps = float(event.step)
        if steps == 0:
            return
        mods = QApplication.keyboardModifiers()
        # Щипок тачпада Windows приходит как Ctrl+колесо — это тоже масштаб.
        if mods & Qt.ShiftModifier and self._info is not None:
            span = max(self._info.vmax - self._info.vmin, 1e-3)
            delta = 0.05 * span * steps
            if mods & Qt.ControlModifier:
                self._update(auto_scale=False, vmin=round(self._info.vmin + delta, 3), vmax=self._info.vmax)
            else:
                self._update(auto_scale=False, vmin=self._info.vmin, vmax=round(self._info.vmax + delta, 3))
        else:
            self._update(zoom=round(min(10.0, max(0.1, self._style.zoom * (1.1 ** steps))), 3))


def _fmt(value) -> str:
    if isinstance(value, float):
        return "%.3g" % value
    if isinstance(value, Enum):
        return value.title
    return str(value)
