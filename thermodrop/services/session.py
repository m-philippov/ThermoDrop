"""Сессия анализа — единый источник состояния приложения.

Представления подписываются на сигналы (паттерн «Наблюдатель») и не
обмениваются данными напрямую. Все изменения состояния журналируются.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal

from thermodrop.core.analysis import compute_histogram, extract_region, to_display
from thermodrop.core.detection import detect_drop
from thermodrop.core.models import (
    EllipseRegion,
    HistogramFilter,
    HistogramResult,
    HistogramSource,
    ReferenceMode,
    RegionData,
    ThermalField,
    ValueMode,
)
from thermodrop.core.reference import make_reference_strategy
from thermodrop.fileio.readers import ReaderRegistry

log = logging.getLogger(__name__)


class AnalysisSession(QObject):
    #: Загружен новый кадр или изменена его ориентация.
    field_changed = pyqtSignal(object)  # ThermalField
    #: Изменился эллипс (в т. ч. в процессе перетаскивания).
    region_changed = pyqtSignal(object)  # EllipseRegion
    #: Пересчитаны данные области (значения, опорная температура, единицы).
    region_data_changed = pyqtSignal(object)  # RegionData
    #: Изменились порог или параметры гистограммы.
    histogram_changed = pyqtSignal()

    def __init__(self, readers: ReaderRegistry, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._readers = readers
        self._field: Optional[ThermalField] = None
        self._region: Optional[EllipseRegion] = None
        self._region_data: Optional[RegionData] = None
        self._value_mode = ValueMode.DELTA
        self._reference_mode = ReferenceMode.BACKGROUND_MEDIAN
        self._manual_reference = 20.0
        self._threshold_abs = 0.0  # порог хранится в абсолютной температуре
        self._bins = 40
        self._hist_source = HistogramSource.REGION
        self._hist_filter = HistogramFilter.ALL

    # ------------------------------------------------------------------ свойства

    @property
    def field(self) -> Optional[ThermalField]:
        return self._field

    @property
    def region(self) -> Optional[EllipseRegion]:
        return self._region

    @property
    def region_data(self) -> Optional[RegionData]:
        return self._region_data

    @property
    def value_mode(self) -> ValueMode:
        return self._value_mode

    @property
    def reference_mode(self) -> ReferenceMode:
        return self._reference_mode

    @property
    def manual_reference(self) -> float:
        return self._manual_reference

    @property
    def reference(self) -> float:
        return self._region_data.reference if self._region_data else 0.0

    @property
    def bins(self) -> int:
        return self._bins

    @property
    def hist_source(self) -> HistogramSource:
        return self._hist_source

    @property
    def hist_filter(self) -> HistogramFilter:
        return self._hist_filter

    @property
    def threshold(self) -> float:
        """Порог в единицах отображения (T или ΔT)."""
        return float(to_display(np.float64(self._threshold_abs), self._value_mode, self.reference))

    @property
    def threshold_absolute(self) -> float:
        return self._threshold_abs

    # ------------------------------------------------------------------ сценарии

    def open_file(self, path: Path) -> ThermalField:
        log.info("Открытие файла: %s", path)
        field = self._readers.read(path)
        self._threshold_abs = float(np.nanmedian(field.data))
        self._apply_field(field, reset_region=True)
        return field

    def transpose(self) -> None:
        self._require_field()
        log.info("Транспонирование кадра")
        self._apply_field(self._field.transposed(), reset_region=True)

    def rotate90(self) -> None:
        self._require_field()
        log.info("Поворот кадра на 90° по часовой стрелке")
        self._apply_field(self._field.rotated90(), reset_region=True)

    def detect_region(self) -> bool:
        """Автоматически ставит эллипс на каплю. Возвращает успех."""
        self._require_field()
        log.info("Автопоиск капли")
        region = detect_drop(self._field)
        if region is None:
            return False
        self.set_region(region)
        return True

    def set_region(self, region: EllipseRegion, final: bool = True) -> None:
        if region == self._region:
            if final:  # перетаскивание завершилось в той же точке — фиксируем итог в журнале
                log.info("Эллипс: %s", region.describe())
            return
        self._region = region
        if final:
            log.info("Эллипс: %s", region.describe())
        else:
            log.debug("Эллипс (перемещение): %s", region.describe())
        self.region_changed.emit(region)
        self._recompute()

    def set_value_mode(self, mode: ValueMode) -> None:
        if mode is self._value_mode:
            return
        log.info("Режим значений: %s", mode.title)
        self._value_mode = mode
        self._recompute()

    def set_reference_mode(self, mode: ReferenceMode) -> None:
        if mode is self._reference_mode:
            return
        log.info("Опорная температура: %s", mode.title)
        self._reference_mode = mode
        self._recompute()

    def set_manual_reference(self, value: float) -> None:
        if value == self._manual_reference:
            return
        log.info("Опорная температура вручную: %.2f °C", value)
        self._manual_reference = float(value)
        if self._reference_mode is ReferenceMode.MANUAL:
            self._recompute()

    def set_threshold(self, value: float, final: bool = True) -> None:
        """Устанавливает порог в единицах отображения.

        Промежуточные значения (``final=False``, перетаскивание) не журналируются,
        итоговое журналируется всегда.
        """
        absolute = float(value) + (self.reference if self._value_mode is ValueMode.DELTA else 0.0)
        changed = absolute != self._threshold_abs
        self._threshold_abs = absolute
        if final:
            log.info("Порог: %.2f (%s), T = %.2f °C", value, self._value_mode.unit_label, absolute)
        if changed:
            self.histogram_changed.emit()

    def set_bins(self, bins: int) -> None:
        if bins == self._bins:
            return
        log.info("Число интервалов гистограммы: %d", bins)
        self._bins = int(bins)
        self.histogram_changed.emit()

    def set_hist_source(self, source: HistogramSource) -> None:
        if source is self._hist_source:
            return
        log.info("Источник гистограммы: %s", source.title)
        self._hist_source = source
        self.histogram_changed.emit()

    def set_hist_filter(self, flt: HistogramFilter) -> None:
        if flt is self._hist_filter:
            return
        log.info("Фильтр гистограммы: %s", flt.title)
        self._hist_filter = flt
        self.histogram_changed.emit()

    def histogram(self) -> Optional[HistogramResult]:
        if self._field is None or self._region_data is None:
            return None
        if self._hist_source is HistogramSource.REGION:
            values = self._region_data.inside
        else:
            values = to_display(self._field.data, self._value_mode, self.reference)
        return compute_histogram(values, self._bins, self.threshold, self._hist_filter)

    # ------------------------------------------------------------------ внутреннее

    def _require_field(self) -> None:
        if self._field is None:
            raise RuntimeError("Файл не загружен")

    def _apply_field(self, field: ThermalField, reset_region: bool) -> None:
        self._field = field
        if reset_region or self._region is None:
            self._region = detect_drop(field) or EllipseRegion.centered_in(field.rows, field.cols)
        self.field_changed.emit(field)
        log.info("Начальный эллипс: %s", self._region.describe())
        self.region_changed.emit(self._region)
        self._recompute()

    def _recompute(self) -> None:
        if self._field is None or self._region is None:
            return
        strategy = make_reference_strategy(self._reference_mode, self._manual_reference)
        previous_ref = self._region_data.reference if self._region_data else None
        self._region_data = extract_region(self._field, self._region, self._value_mode, strategy)
        if previous_ref is None or abs(previous_ref - self._region_data.reference) > 1e-9:
            log.debug("Опорная температура Tоп = %.3f °C", self._region_data.reference)
        self.region_data_changed.emit(self._region_data)
        self.histogram_changed.emit()
