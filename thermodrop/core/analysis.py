"""Вычисления над полем: вырезка области, гистограмма, укрупнение сетки."""

from __future__ import annotations

from typing import Tuple

import numpy as np

from thermodrop.core.geometry import bounding_box, ellipse_mask
from thermodrop.core.models import (
    EllipseRegion,
    HistogramFilter,
    HistogramResult,
    RegionData,
    Statistics,
    ThermalField,
    ValueMode,
)
from thermodrop.core.reference import ReferenceStrategy


def extract_region(field: ThermalField, region: EllipseRegion,
                   mode: ValueMode, reference: ReferenceStrategy) -> RegionData:
    """Вырезает область эллипса и переводит значения в единицы отображения."""
    full_mask = ellipse_mask(region, field.rows, field.cols)
    ref = reference.compute(field.data, full_mask)
    row0, row1, col0, col1 = bounding_box(region, field.rows, field.cols)
    values = field.data[row0:row1, col0:col1].astype(float)
    if mode is ValueMode.DELTA:
        values = values - ref
    return RegionData(values=values, mask=full_mask[row0:row1, col0:col1].copy(),
                      row0=row0, col0=col0, reference=ref, mode=mode)


def to_display(values: np.ndarray, mode: ValueMode, reference: float) -> np.ndarray:
    return values - reference if mode is ValueMode.DELTA else values


def select(values: np.ndarray, threshold: float, flt: HistogramFilter) -> np.ndarray:
    v = values[np.isfinite(values)]
    if flt is HistogramFilter.ABOVE:
        return v[v >= threshold]
    if flt is HistogramFilter.BELOW:
        return v[v < threshold]
    return v


def compute_histogram(values: np.ndarray, bins: int, threshold: float,
                      flt: HistogramFilter) -> HistogramResult:
    """Гистограмма значений с учётом фильтра по порогу.

    Границы корзин строятся по всему набору, чтобы при смене фильтра
    шкала не «прыгала».
    """
    all_values = np.asarray(values, dtype=float).ravel()
    all_values = all_values[np.isfinite(all_values)]
    chosen = select(all_values, threshold, flt)
    if all_values.size:
        lo, hi = float(all_values.min()), float(all_values.max())
        if hi <= lo:
            lo, hi = lo - 0.5, hi + 0.5
        edges = np.linspace(lo, hi, int(bins) + 1)
    else:
        edges = np.linspace(0.0, 1.0, int(bins) + 1)
    counts, _ = np.histogram(chosen, bins=edges)
    counts_all, _ = np.histogram(all_values, bins=edges)
    fraction = chosen.size / all_values.size if all_values.size else 0.0
    return HistogramResult(counts=counts, counts_all=counts_all, edges=edges,
                           threshold=float(threshold), filter=flt,
                           selected=Statistics.of(chosen), total=Statistics.of(all_values),
                           fraction_selected=float(fraction))


def block_reduce(values: np.ndarray, mask: np.ndarray, factor: int,
                 min_fill: float = 0.5) -> Tuple[np.ndarray, np.ndarray]:
    """Укрупняет сетку в ``factor`` раз (среднее по пикселям внутри маски).

    Блок считается внутренним, если доля внутренних пикселей ≥ ``min_fill``.
    """
    if factor <= 1:
        return values, mask
    rows, cols = values.shape
    pr, pc = (-rows) % factor, (-cols) % factor
    v = np.pad(values.astype(float), ((0, pr), (0, pc)), constant_values=np.nan)
    m = np.pad(mask, ((0, pr), (0, pc)), constant_values=False)
    br, bc = v.shape[0] // factor, v.shape[1] // factor
    v = v.reshape(br, factor, bc, factor)
    m = m.reshape(br, factor, bc, factor)
    inside = np.where(m, v, 0.0)
    n_inside = m.sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = inside.sum(axis=(1, 3)) / n_inside
    block_mask = n_inside >= min_fill * factor * factor
    return np.where(block_mask, mean, np.nan), block_mask


def auto_block_factor(shape: Tuple[int, int], max_cells: int) -> int:
    """Минимальный коэффициент укрупнения, при котором клеток не больше ``max_cells``."""
    rows, cols = shape
    factor = 1
    while (-(-rows // factor)) * (-(-cols // factor)) > max_cells:
        factor += 1
    return factor
