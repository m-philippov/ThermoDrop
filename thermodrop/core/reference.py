"""Стратегии вычисления опорной температуры (паттерн «Стратегия»)."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from thermodrop.core.models import ReferenceMode


class ReferenceStrategy(ABC):
    """Вычисляет опорную температуру по кадру и маске эллипса (маска на весь кадр)."""

    mode: ReferenceMode

    @abstractmethod
    def compute(self, data: np.ndarray, mask: np.ndarray) -> float:
        raise NotImplementedError


def _finite(values: np.ndarray) -> np.ndarray:
    return values[np.isfinite(values)]


class BackgroundMedianReference(ReferenceStrategy):
    mode = ReferenceMode.BACKGROUND_MEDIAN

    def compute(self, data: np.ndarray, mask: np.ndarray) -> float:
        outside = _finite(data[~mask])
        return float(np.median(outside)) if outside.size else float(np.nanmedian(data))


class RegionMaxReference(ReferenceStrategy):
    mode = ReferenceMode.REGION_MAX

    def compute(self, data: np.ndarray, mask: np.ndarray) -> float:
        inside = _finite(data[mask])
        return float(inside.max()) if inside.size else float(np.nanmax(data))


class RegionMinReference(ReferenceStrategy):
    mode = ReferenceMode.REGION_MIN

    def compute(self, data: np.ndarray, mask: np.ndarray) -> float:
        inside = _finite(data[mask])
        return float(inside.min()) if inside.size else float(np.nanmin(data))


class FrameMedianReference(ReferenceStrategy):
    mode = ReferenceMode.FRAME_MEDIAN

    def compute(self, data: np.ndarray, mask: np.ndarray) -> float:
        return float(np.nanmedian(data))


class ManualReference(ReferenceStrategy):
    mode = ReferenceMode.MANUAL

    def __init__(self, value: float) -> None:
        self.value = float(value)

    def compute(self, data: np.ndarray, mask: np.ndarray) -> float:
        return self.value


def make_reference_strategy(mode: ReferenceMode, manual_value: float = 0.0) -> ReferenceStrategy:
    """Фабрика стратегий опорной температуры."""
    if mode is ReferenceMode.MANUAL:
        return ManualReference(manual_value)
    simple = {
        ReferenceMode.BACKGROUND_MEDIAN: BackgroundMedianReference,
        ReferenceMode.REGION_MAX: RegionMaxReference,
        ReferenceMode.REGION_MIN: RegionMinReference,
        ReferenceMode.FRAME_MEDIAN: FrameMedianReference,
    }
    return simple[mode]()
