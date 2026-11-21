"""Доменные модели."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class ThermalField:
    """Температурное поле кадра тепловизора.

    ``data[row, col]`` — температура в °C. Строка 0 — верх кадра.
    """

    data: np.ndarray
    source: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.data.ndim != 2:
            raise ValueError("Температурное поле должно быть двумерным, получено ndim=%d" % self.data.ndim)
        if self.data.size == 0:
            raise ValueError("Температурное поле пустое")

    @property
    def rows(self) -> int:
        return int(self.data.shape[0])

    @property
    def cols(self) -> int:
        return int(self.data.shape[1])

    @property
    def name(self) -> str:
        return self.source.name if self.source else "<без имени>"

    def transposed(self) -> "ThermalField":
        return ThermalField(np.ascontiguousarray(self.data.T), self.source)

    def rotated90(self) -> "ThermalField":
        """Поворот на 90° по часовой стрелке."""
        return ThermalField(np.ascontiguousarray(np.rot90(self.data, k=-1)), self.source)


@dataclass(frozen=True)
class EllipseRegion:
    """Эллиптическая область в пиксельных координатах кадра.

    Ось X — вдоль столбцов, ось Y — вдоль строк (вниз). Пиксель (row, col)
    занимает квадрат [col, col+1] × [row, row+1]. Угол — в градусах,
    поворот полуоси ``rx`` от оси X к оси Y.
    """

    cx: float
    cy: float
    rx: float
    ry: float
    angle_deg: float = 0.0

    def __post_init__(self) -> None:
        if self.rx <= 0 or self.ry <= 0:
            raise ValueError("Полуоси эллипса должны быть положительными")

    @classmethod
    def centered_in(cls, rows: int, cols: int, fraction: float = 0.25) -> "EllipseRegion":
        r = max(1.0, min(rows, cols) * fraction)
        return cls(cx=cols / 2.0, cy=rows / 2.0, rx=r, ry=r, angle_deg=0.0)

    @property
    def area(self) -> float:
        return math.pi * self.rx * self.ry

    def describe(self) -> str:
        return "центр=(%.1f; %.1f), полуоси=(%.1f; %.1f), угол=%.1f°" % (
            self.cx, self.cy, self.rx, self.ry, self.angle_deg)


class ValueMode(Enum):
    """Что отображается: абсолютная температура или отклонение от опорной."""

    ABSOLUTE = "absolute"
    DELTA = "delta"

    @property
    def title(self) -> str:
        return {ValueMode.ABSOLUTE: "T, °C", ValueMode.DELTA: "ΔT = T − Tоп, °C"}[self]

    @property
    def unit_label(self) -> str:
        return {ValueMode.ABSOLUTE: "T, °C", ValueMode.DELTA: "ΔT, °C"}[self]


class ReferenceMode(Enum):
    """Способ определения опорной температуры Tоп для режима ΔT."""

    BACKGROUND_MEDIAN = "background_median"
    REGION_MAX = "region_max"
    REGION_MIN = "region_min"
    FRAME_MEDIAN = "frame_median"
    MANUAL = "manual"

    @property
    def title(self) -> str:
        return {
            ReferenceMode.BACKGROUND_MEDIAN: "Медиана фона (вне эллипса)",
            ReferenceMode.REGION_MAX: "Максимум в эллипсе",
            ReferenceMode.REGION_MIN: "Минимум в эллипсе",
            ReferenceMode.FRAME_MEDIAN: "Медиана всего кадра",
            ReferenceMode.MANUAL: "Вручную",
        }[self]


class HistogramSource(Enum):
    REGION = "region"
    FRAME = "frame"

    @property
    def title(self) -> str:
        return {HistogramSource.REGION: "Эллипс", HistogramSource.FRAME: "Весь кадр"}[self]


class HistogramFilter(Enum):
    ALL = "all"
    ABOVE = "above"
    BELOW = "below"

    @property
    def title(self) -> str:
        return {
            HistogramFilter.ALL: "Все значения",
            HistogramFilter.ABOVE: "Выше порога",
            HistogramFilter.BELOW: "Ниже порога",
        }[self]


@dataclass(frozen=True)
class RegionData:
    """Данные, вырезанные по ограничивающему прямоугольнику эллипса.

    ``values`` — значения в единицах отображения (T или ΔT),
    ``mask`` — True для пикселей внутри эллипса,
    ``row0``/``col0`` — смещение прямоугольника в кадре.
    """

    values: np.ndarray
    mask: np.ndarray
    row0: int
    col0: int
    reference: float
    mode: ValueMode

    @property
    def inside(self) -> np.ndarray:
        return self.values[self.mask]

    @property
    def is_empty(self) -> bool:
        return not bool(self.mask.any())


@dataclass(frozen=True)
class Statistics:
    count: int
    minimum: float
    maximum: float
    mean: float
    median: float
    std: float

    @classmethod
    def of(cls, values: np.ndarray) -> "Statistics":
        v = np.asarray(values, dtype=float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            nan = float("nan")
            return cls(0, nan, nan, nan, nan, nan)
        return cls(int(v.size), float(v.min()), float(v.max()), float(v.mean()),
                   float(np.median(v)), float(v.std()))


@dataclass(frozen=True)
class HistogramResult:
    """``counts`` — отобранные фильтром значения, ``counts_all`` — все значения."""

    counts: np.ndarray
    counts_all: np.ndarray
    edges: np.ndarray
    threshold: float
    filter: HistogramFilter
    selected: Statistics
    total: Statistics
    fraction_selected: float = field(default=0.0)

    @property
    def centers(self) -> np.ndarray:
        return 0.5 * (self.edges[:-1] + self.edges[1:])
