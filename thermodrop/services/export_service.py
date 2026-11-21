"""Сценарии экспорта: изображения (через те же рендереры, что и на экране) и CSV."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from thermodrop.core.models import HistogramResult, RegionData
from thermodrop.fileio import exporters
from thermodrop.rendering.bar3d import Bar3DRenderer, Bar3DStyle
from thermodrop.rendering.histogram import HistogramRenderer, HistogramStyle
from thermodrop.rendering.labels import AxisLabels

log = logging.getLogger(__name__)

IMAGE_FILTER = ("PNG (*.png);;JPEG (*.jpg *.jpeg);;TIFF (*.tif *.tiff);;"
                "SVG — вектор (*.svg);;PDF — вектор (*.pdf)")
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".svg", ".pdf"}


@dataclass(frozen=True)
class ImageOptions:
    width_px: int = 1920
    height_px: int = 880
    dpi: int = 150
    transparent: bool = False
    title: str = ""
    labels: AxisLabels = AxisLabels()
    #: None — как на экране.
    show_axes: Optional[bool] = None


class ExportService:
    def __init__(self, bar3d: Bar3DRenderer, histogram: HistogramRenderer) -> None:
        self._bar3d = bar3d
        self._histogram = histogram

    def export_bar3d(self, path: Path, data: RegionData, style: Bar3DStyle,
                     threshold: Optional[float], options: ImageOptions) -> None:
        if options.show_axes is not None:
            style = style.with_(show_axes=options.show_axes)
        self._save(path, options, lambda fig: self._bar3d.render(
            fig, data, style, threshold, title=options.title, labels=options.labels))
        log.info("3D-изображение сохранено: %s (%d×%d, %d dpi, вид %.1f°/%.1f°)",
                 path, options.width_px, options.height_px, options.dpi, style.elev, style.azim)
        log.info("Параметры экспорта: заголовок=%r, оси=%s, подписи=%s", options.title, style.show_axes,
                 options.labels)

    def export_histogram_image(self, path: Path, hist: HistogramResult, style: HistogramStyle,
                               unit_label: str, options: ImageOptions) -> None:
        def draw(fig: Figure) -> None:
            self._histogram.render(fig, hist, style.with_(show_stats=True), unit_label, compact=False,
                                   labels=options.labels)
            if options.title:
                fig.suptitle(options.title)
                fig.tight_layout()

        self._save(path, options, draw)
        log.info("Гистограмма сохранена: %s (%d×%d, %d dpi)", path, options.width_px, options.height_px,
                 options.dpi)
        log.info("Параметры экспорта: заголовок=%r, подписи=%s", options.title, options.labels)

    @staticmethod
    def export_region_matrix(path: Path, data: RegionData) -> None:
        exporters.export_region_matrix(path, data)

    @staticmethod
    def export_region_points(path: Path, data: RegionData) -> None:
        exporters.export_region_points(path, data)

    @staticmethod
    def export_histogram_csv(path: Path, hist: HistogramResult, unit_label: str) -> None:
        exporters.export_histogram(path, hist, unit_label)

    @staticmethod
    def _save(path: Path, options: ImageOptions, draw: Callable[[Figure], object]) -> None:
        if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError("Неподдерживаемый формат изображения: %s" % path.suffix)
        dpi = max(30, int(options.dpi))
        fig = Figure(figsize=(options.width_px / dpi, options.height_px / dpi), dpi=dpi)
        FigureCanvasAgg(fig)
        draw(fig)
        fig.savefig(str(path), dpi=dpi, transparent=options.transparent,
                    facecolor="none" if options.transparent else "white")
