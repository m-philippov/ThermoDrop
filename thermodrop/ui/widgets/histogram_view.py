"""Окно 3: гистограмма температур с перетаскиваемой линией порога."""

from __future__ import annotations

import logging
from typing import Optional

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from thermodrop.core.models import HistogramFilter, HistogramResult, HistogramSource
from thermodrop.rendering.histogram import HistogramArtists, HistogramRenderer, HistogramStyle
from thermodrop.services.session import AnalysisSession
from thermodrop.ui.widgets.common import Debouncer, double_spin, enum_combo, int_spin, select_data, signals_blocked

log = logging.getLogger(__name__)


class HistogramView(QWidget):
    export_image_requested = pyqtSignal()
    export_csv_requested = pyqtSignal()

    def __init__(self, session: AnalysisSession, renderer: HistogramRenderer,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._session = session
        self._renderer = renderer
        self._style = HistogramStyle()
        self._artists: Optional[HistogramArtists] = None
        self._hist: Optional[HistogramResult] = None
        self._dragging = False

        self._figure = Figure(figsize=(10, 2), dpi=100)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._canvas.setMinimumHeight(110)
        self._canvas.setToolTip("ЛКМ — перетащить линию порога (или щёлкнуть в нужное место)")
        self._canvas.mpl_connect("button_press_event", self._on_press)
        self._canvas.mpl_connect("motion_notify_event", self._on_motion)
        self._canvas.mpl_connect("button_release_event", self._on_release)
        self._canvas.mpl_connect("resize_event", lambda _e: self._redraw.trigger())

        self._redraw = Debouncer(40, self._render, self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._build_panel())
        layout.addWidget(self._canvas, 1)
        layout.addWidget(self._build_stats())

        session.histogram_changed.connect(self._redraw.trigger)
        self._sync_controls()
        self._render()

    @property
    def style(self) -> HistogramStyle:
        return self._style

    @property
    def result(self) -> Optional[HistogramResult]:
        return self._hist

    # ------------------------------------------------------------------ панели

    def _build_panel(self) -> QWidget:
        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setVerticalSpacing(2)

        self._source = enum_combo(HistogramSource)
        self._source.currentIndexChanged.connect(
            lambda _: self._session.set_hist_source(self._source.currentData()))
        self._filter = enum_combo(HistogramFilter)
        self._filter.currentIndexChanged.connect(
            lambda _: self._session.set_hist_filter(self._filter.currentData()))
        self._bins = int_spin(2, 500, tooltip="Число интервалов")
        self._bins.valueChanged.connect(self._session.set_bins)
        self._threshold = double_spin(-1e4, 1e4, 0.1, 2, tooltip="Порог (или перетащите линию)")
        self._threshold.valueChanged.connect(lambda v: self._session.set_threshold(v, final=True))

        self._vertical = QCheckBox("T по вертикали")
        self._vertical.setToolTip("Температура по вертикальной оси, порог — горизонтальная линия")
        self._vertical.toggled.connect(lambda on: self._update_style(values_vertical=on))
        self._log = QCheckBox("Лог. шкала")
        self._log.toggled.connect(lambda on: self._update_style(log_scale=on))
        self._colored = QCheckBox("Цвет")
        self._colored.toggled.connect(lambda on: self._update_style(colored=on))

        grid.addWidget(QLabel("Данные:"), 0, 0)
        grid.addWidget(self._source, 0, 1)
        grid.addWidget(QLabel("Отбор:"), 1, 0)
        grid.addWidget(self._filter, 1, 1)
        grid.addWidget(QLabel("Порог:"), 2, 0)
        grid.addWidget(self._threshold, 2, 1)
        grid.addWidget(QLabel("Интерв.:"), 3, 0)
        grid.addWidget(self._bins, 3, 1)
        flags = QHBoxLayout()
        flags.addWidget(self._vertical)
        grid.addLayout(flags, 4, 0, 1, 2)
        flags2 = QHBoxLayout()
        flags2.addWidget(self._log)
        flags2.addWidget(self._colored)
        grid.addLayout(flags2, 5, 0, 1, 2)
        panel.setMaximumWidth(250)
        return panel

    def _build_stats(self) -> QWidget:
        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(0, 0, 0, 0)
        self._stats = QLabel("—")
        self._stats.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._stats.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._stats.setMinimumWidth(200)
        img = QPushButton("Экспорт PNG…")
        img.clicked.connect(self.export_image_requested.emit)
        csv = QPushButton("Экспорт CSV…")
        csv.clicked.connect(self.export_csv_requested.emit)
        grid.addWidget(self._stats, 0, 0, 1, 2)
        grid.addWidget(img, 1, 0)
        grid.addWidget(csv, 1, 1)
        grid.setRowStretch(0, 1)
        panel.setMaximumWidth(280)
        return panel

    def _sync_controls(self) -> None:
        s = self._session
        select_data(self._source, s.hist_source)
        select_data(self._filter, s.hist_filter)
        with signals_blocked(self._bins, self._vertical, self._log, self._colored):
            self._bins.setValue(s.bins)
            self._vertical.setChecked(self._style.values_vertical)
            self._log.setChecked(self._style.log_scale)
            self._colored.setChecked(self._style.colored)

    def _update_style(self, **changes) -> None:
        self._style = self._style.with_(**changes)
        log.info("Гистограмма: %s", ", ".join("%s=%s" % kv for kv in sorted(changes.items())))
        self._redraw.trigger()

    def set_colormap(self, name: str) -> None:
        if name != self._style.cmap:
            self._style = self._style.with_(cmap=name)
            self._redraw.trigger()

    # ------------------------------------------------------------------ отрисовка

    def _render(self) -> None:
        self._sync_controls()
        self._hist = self._session.histogram()
        unit = self._session.value_mode.unit_label
        self._artists = self._renderer.render(self._figure, self._hist, self._style, unit)
        self._canvas.draw_idle()
        if self._hist is None:
            self._stats.setText("—")
            return
        with signals_blocked(self._threshold):
            self._threshold.setValue(self._hist.threshold)
        s, t = self._hist.selected, self._hist.total
        self._stats.setText(
            "<b>%s</b> (%s)<br>"
            "N = %d из %d (%.1f%%)<br>"
            "мин %.2f, макс %.2f<br>"
            "среднее %.2f, медиана %.2f<br>"
            "СКО %.3f" % (
                self._hist.filter.title, unit, s.count, t.count, 100 * self._hist.fraction_selected,
                s.minimum, s.maximum, s.mean, s.median, s.std))

    # ------------------------------------------------------------------ перетаскивание порога

    def _value_from_event(self, event) -> Optional[float]:
        if self._artists is None or event.inaxes is not self._artists.ax:
            return None
        value = event.ydata if self._style.values_vertical else event.xdata
        return None if value is None else float(value)

    def _move_line(self, value: float) -> None:
        line = self._artists.threshold_line
        if self._style.values_vertical:
            line.set_ydata([value, value])
        else:
            line.set_xdata([value, value])
        self._canvas.draw_idle()

    def _on_press(self, event) -> None:
        if event.button != 1:
            return
        value = self._value_from_event(event)
        if value is None:
            return
        self._dragging = True
        self._move_line(value)
        self._session.set_threshold(value, final=False)

    def _on_motion(self, event) -> None:
        if not self._dragging:
            return
        value = self._value_from_event(event)
        if value is None:
            return
        self._move_line(value)
        self._session.set_threshold(value, final=False)

    def _on_release(self, event) -> None:
        if not self._dragging:
            return
        self._dragging = False
        value = self._value_from_event(event)
        if value is None:
            value = self._session.threshold
        self._session.set_threshold(value, final=True)
