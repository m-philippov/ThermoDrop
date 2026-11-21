"""Геометрия эллиптической области: маска, ограничивающий прямоугольник,
перемещение, поворот и изменение размера перетаскиванием."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Tuple

import numpy as np

from thermodrop.core.models import EllipseRegion

BBox = Tuple[int, int, int, int]  # row0, row1, col0, col1 (полуинтервалы)


def bounding_box(region: EllipseRegion, rows: int, cols: int) -> BBox:
    """Целочисленный прямоугольник, содержащий эллипс, обрезанный по кадру."""
    a = math.radians(region.angle_deg)
    cos_a, sin_a = math.cos(a), math.sin(a)
    half_w = math.hypot(region.rx * cos_a, region.ry * sin_a)
    half_h = math.hypot(region.rx * sin_a, region.ry * cos_a)
    col0 = max(0, int(math.floor(region.cx - half_w)))
    col1 = min(cols, int(math.ceil(region.cx + half_w)))
    row0 = max(0, int(math.floor(region.cy - half_h)))
    row1 = min(rows, int(math.ceil(region.cy + half_h)))
    return row0, max(row0, row1), col0, max(col0, col1)


MIN_SEMI_AXIS = 0.5
#: Если точка захвата ближе к центру по оси, чем эта доля полуоси, ось не масштабируется.
GRAB_AXIS_FRACTION = 0.2

Point = Tuple[float, float]


def normalize_angle(angle_deg: float) -> float:
    """Угол в диапазоне (−180; 180]."""
    a = math.fmod(angle_deg, 360.0)
    if a <= -180.0:
        a += 360.0
    elif a > 180.0:
        a -= 360.0
    return a


def to_local(region: EllipseRegion, point: Point) -> Point:
    """Координаты точки в системе эллипса (центр в начале, ось u вдоль rx)."""
    a = math.radians(region.angle_deg)
    dx, dy = point[0] - region.cx, point[1] - region.cy
    return dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)


def from_local(region: EllipseRegion, local: Point) -> Point:
    a = math.radians(region.angle_deg)
    u, v = local
    return region.cx + u * math.cos(a) - v * math.sin(a), region.cy + u * math.sin(a) + v * math.cos(a)


def moved(region: EllipseRegion, start: Point, current: Point) -> EllipseRegion:
    return replace(region, cx=region.cx + current[0] - start[0], cy=region.cy + current[1] - start[1])


def rotated(region: EllipseRegion, start: Point, current: Point) -> EllipseRegion:
    a0 = math.atan2(start[1] - region.cy, start[0] - region.cx)
    a1 = math.atan2(current[1] - region.cy, current[0] - region.cx)
    return replace(region, angle_deg=normalize_angle(region.angle_deg + math.degrees(a1 - a0)))


def resized(region: EllipseRegion, start: Point, current: Point, uniform: bool = False) -> EllipseRegion:
    """Меняет полуоси так, чтобы точка захвата ``start`` следовала за курсором.

    Ось масштабируется, только если точка захвата заметно удалена от центра вдоль неё
    (иначе мелкое смещение давало бы огромный коэффициент). ``uniform`` — с сохранением пропорций.
    """
    u0, v0 = to_local(region, start)
    u1, v1 = to_local(region, current)
    if uniform:
        r0 = math.hypot(u0 / region.rx, v0 / region.ry)
        if r0 < GRAB_AXIS_FRACTION:
            return region
        k = math.hypot(u1 / region.rx, v1 / region.ry) / r0
        return replace(region, rx=max(MIN_SEMI_AXIS, region.rx * k), ry=max(MIN_SEMI_AXIS, region.ry * k))
    rx, ry = region.rx, region.ry
    if abs(u0) >= GRAB_AXIS_FRACTION * region.rx:
        rx = max(MIN_SEMI_AXIS, region.rx * abs(u1) / abs(u0))
    if abs(v0) >= GRAB_AXIS_FRACTION * region.ry:
        ry = max(MIN_SEMI_AXIS, region.ry * abs(v1) / abs(v0))
    return replace(region, rx=rx, ry=ry)


def ellipse_mask(region: EllipseRegion, rows: int, cols: int,
                 row0: int = 0, col0: int = 0) -> np.ndarray:
    """Маска пикселей (по их центрам), попадающих в эллипс.

    Маска строится для окна ``rows × cols`` со смещением ``row0``/``col0``
    относительно начала кадра.
    """
    y = np.arange(row0, row0 + rows, dtype=float)[:, None] + 0.5 - region.cy
    x = np.arange(col0, col0 + cols, dtype=float)[None, :] + 0.5 - region.cx
    a = math.radians(region.angle_deg)
    cos_a, sin_a = math.cos(a), math.sin(a)
    # Переход в систему координат эллипса (поворот на −angle).
    u = x * cos_a + y * sin_a
    v = -x * sin_a + y * cos_a
    return (u / region.rx) ** 2 + (v / region.ry) ** 2 <= 1.0
