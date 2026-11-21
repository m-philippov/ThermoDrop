"""Автоматический поиск капли и подбор эллипса.

Алгоритм: порог посередине между фоном (медианой кадра) и экстремумом,
морфологическое открытие (отсекает тонкую нить подвеса), связная
компонента, содержащая экстремум, эллипс по вторым моментам.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

from thermodrop.core.models import EllipseRegion, ThermalField

log = logging.getLogger(__name__)


def _shift_and(mask: np.ndarray, radius: int) -> np.ndarray:
    """Эрозия квадратным элементом (2r+1)×(2r+1)."""
    out = mask.copy()
    padded = np.pad(mask, radius, constant_values=False)
    rows, cols = mask.shape
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            out &= padded[radius + dr:radius + dr + rows, radius + dc:radius + dc + cols]
    return out


def _shift_or(mask: np.ndarray, radius: int) -> np.ndarray:
    """Дилатация квадратным элементом (2r+1)×(2r+1)."""
    out = mask.copy()
    padded = np.pad(mask, radius, constant_values=False)
    rows, cols = mask.shape
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            out |= padded[radius + dr:radius + dr + rows, radius + dc:radius + dc + cols]
    return out


def _component(mask: np.ndarray, seed: tuple) -> np.ndarray:
    """Связная компонента (4-связность), содержащая ``seed``, — заливкой через дилатацию."""
    region = np.zeros_like(mask)
    if not mask[seed]:
        return region
    region[seed] = True
    while True:
        grown = region.copy()
        grown[1:, :] |= region[:-1, :]
        grown[:-1, :] |= region[1:, :]
        grown[:, 1:] |= region[:, :-1]
        grown[:, :-1] |= region[:, 1:]
        grown &= mask
        if np.array_equal(grown, region):
            return region
        region = grown


def detect_drop(field: ThermalField, opening_radius: int = 2, margin: float = 1.15) -> Optional[EllipseRegion]:
    data = np.where(np.isfinite(field.data), field.data, np.nanmedian(field.data))
    background = float(np.median(data))
    lo, hi = float(data.min()), float(data.max())
    cold = (background - lo) >= (hi - background)
    extreme = lo if cold else hi
    if abs(extreme - background) < 1e-6:
        log.warning("Автопоиск: кадр однородный, капля не найдена")
        return None

    level = 0.5 * (background + extreme)
    mask = data <= level if cold else data >= level
    opened = _shift_or(_shift_and(mask, opening_radius), opening_radius) & mask
    if not opened.any():
        opened = mask

    candidates = np.where(opened, data if cold else -data, np.inf)
    seed = np.unravel_index(int(np.argmin(candidates)), data.shape)
    blob = _component(opened, seed)
    n = int(blob.sum())
    if n < 5:
        log.warning("Автопоиск: слишком маленькая область (%d пикс.)", n)
        return None

    rr, cc = np.nonzero(blob)
    y, x = rr + 0.5, cc + 0.5
    cy, cx = float(y.mean()), float(x.mean())
    cov = np.cov(np.vstack([x - cx, y - cy]))
    eigval, eigvec = np.linalg.eigh(cov)
    # Для равномерно заполненного эллипса дисперсия вдоль полуоси a равна a²/4.
    ry, rx = (2.0 * math.sqrt(max(v, 0.25)) * margin for v in eigval)
    vx, vy = eigvec[:, 1]
    angle = math.degrees(math.atan2(vy, vx))
    if angle > 90:
        angle -= 180
    elif angle <= -90:
        angle += 180
    region = EllipseRegion(cx=cx, cy=cy, rx=rx, ry=ry, angle_deg=angle)
    log.info("Автопоиск: %s капля, %d пикс., фон %.2f °C, экстремум %.2f °C → %s",
             "холодная" if cold else "горячая", n, background, extreme, region.describe())
    return region
