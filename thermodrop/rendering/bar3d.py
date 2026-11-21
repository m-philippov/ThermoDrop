"""Трёхмерная столбчатая диаграмма области (аналог MATLAB ``bar3``)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional, Tuple

import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (регистрирует проекцию 3d)
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from thermodrop.core.analysis import auto_block_factor, block_reduce
from thermodrop.core.models import RegionData, ValueMode
from thermodrop.rendering.colormaps import DEFAULT_COLORMAP, get_colormap
from thermodrop.rendering.labels import AxisLabels, pick


class ZDirection(Enum):
    AUTO = "auto"
    NORMAL = "normal"
    INVERTED = "inverted"

    @property
    def title(self) -> str:
        return {
            ZDirection.AUTO: "Авто (столбцы вверх)",
            ZDirection.NORMAL: "Ось Z вверх",
            ZDirection.INVERTED: "Ось Z вниз",
        }[self]


@dataclass(frozen=True)
class Bar3DStyle:
    """Параметры отображения 3D-диаграммы (неизменяемый объект-значение)."""

    cmap: str = DEFAULT_COLORMAP
    auto_scale: bool = True
    vmin: float = -2.5
    vmax: float = 0.0
    elev: float = 30.0
    azim: float = -37.5
    roll: float = 0.0
    zoom: float = 1.0
    z_aspect: float = 0.6
    bar_width: float = 1.0
    tile_width: float = 0.8
    gradient: bool = True
    segments: int = 6
    show_base: bool = True
    show_edges: bool = True
    show_axes: bool = False
    show_colorbar: bool = True
    z_direction: ZDirection = ZDirection.AUTO
    block: int = 0  # 0 — автоматически
    max_cells: int = 1600
    hide_below_threshold: bool = False

    def with_(self, **changes) -> "Bar3DStyle":
        return replace(self, **changes)


DEFAULT_X_LABEL = "Столбец, пикс."
DEFAULT_Y_LABEL = "Строка, пикс."


@dataclass(frozen=True)
class Bar3DInfo:
    """Фактические параметры последней отрисовки."""

    vmin: float
    vmax: float
    base: float
    block: int
    cells: int
    inverted: bool
    #: Соотношение сторон короба без учёта масштаба (для изменения масштаба без перерисовки).
    box_aspect: Tuple[float, float, float] = (1.0, 1.0, 1.0)


class Bar3DRenderer:
    EDGE_COLOR = (0.0, 0.0, 0.0, 1.0)
    EDGE_WIDTH = 0.35

    def render(self, fig: Figure, data: Optional[RegionData], style: Bar3DStyle,
               threshold: Optional[float] = None, title: str = "",
               labels: AxisLabels = AxisLabels()) -> Optional[Bar3DInfo]:
        fig.clear()
        fig.set_facecolor("white")
        if data is None or data.is_empty:
            fig.text(0.5, 0.5, "Нет данных: откройте файл и выделите область",
                     ha="center", va="center", color="0.4")
            return None

        block = style.block if style.block > 0 else auto_block_factor(data.values.shape, style.max_cells)
        values, mask = block_reduce(data.values, data.mask, block)
        inside = values[mask]
        base = 0.0 if data.mode is ValueMode.DELTA else float(np.nanmin(inside))
        vmin, vmax = self._scale(inside, base, style)
        if not style.auto_scale and data.mode is ValueMode.ABSOLUTE:
            base = vmin

        bars = mask.copy()
        if style.hide_below_threshold and threshold is not None:
            bars &= values >= threshold

        inverted = self._is_inverted(style.z_direction, inside, base)
        # Явная раскладка: шкала не «сдвигает» диаграмму при скрытых осях.
        right = 0.84 if style.show_colorbar else 1.0
        top_edge = 0.93 if title else 1.0
        ax = fig.add_axes([0.0, 0.0, right, top_edge], projection="3d")
        cmap = get_colormap(style.cmap)
        norm = Normalize(vmin=vmin, vmax=vmax, clip=True)

        polys, faces, edges = self._build(values, bars, mask, base, data, block, style, cmap, norm)
        coll = Poly3DCollection(polys, facecolors=faces, edgecolors=edges,
                                linewidths=self.EDGE_WIDTH if style.show_edges else 0.0)
        ax.add_collection3d(coll)

        aspect = self._setup_axes(ax, values.shape, data, block, base, vmin, vmax, inverted, style, labels)
        if style.show_colorbar:
            sm = ScalarMappable(norm=norm, cmap=cmap)
            sm.set_array(np.array([vmin, vmax]))
            cax = fig.add_axes([0.87, 0.12, 0.022, 0.76 * top_edge])
            cbar = fig.colorbar(sm, cax=cax)
            cbar.set_label(pick(labels.colorbar, data.mode.unit_label))
        if title:
            fig.suptitle(title, fontsize=10)
        return Bar3DInfo(vmin=vmin, vmax=vmax, base=base, block=block,
                         cells=int(mask.sum()), inverted=inverted, box_aspect=aspect)

    # ------------------------------------------------------------------ шкала

    @staticmethod
    def _scale(inside: np.ndarray, base: float, style: Bar3DStyle) -> Tuple[float, float]:
        if not style.auto_scale:
            lo, hi = float(style.vmin), float(style.vmax)
        else:
            finite = inside[np.isfinite(inside)]
            lo = float(finite.min()) if finite.size else base
            hi = float(finite.max()) if finite.size else base + 1.0
            lo, hi = min(lo, base), max(hi, base)
        if hi <= lo:
            hi = lo + 1e-3
        return lo, hi

    @staticmethod
    def _is_inverted(direction: ZDirection, inside: np.ndarray, base: float) -> bool:
        if direction is ZDirection.INVERTED:
            return True
        if direction is ZDirection.NORMAL:
            return False
        finite = inside[np.isfinite(inside)]
        return bool(finite.size) and float(np.mean(finite - base)) < 0

    # ------------------------------------------------------------------ геометрия

    def _build(self, values, bars, mask, base, data: RegionData, block: int,
               style: Bar3DStyle, cmap, norm):
        rows, cols = values.shape
        rr, cc = np.nonzero(bars)
        n = rr.size
        w = float(np.clip(style.bar_width, 0.05, 1.0)) * block
        offset = (block - w) / 2.0
        # Скрытые части граней отсекаются только у сплошных столбцов: сквозь зазоры они видны.
        cull = style.bar_width >= 0.999
        x0 = data.col0 + cc * block + offset
        y0 = data.row0 + rr * block + offset
        x1, y1 = x0 + w, y0 + w
        top = np.clip(values[rr, cc], norm.vmin, norm.vmax) if n else np.empty(0)

        polys = []
        faces = []
        edges = []

        # Верхние грани столбцов.
        if n:
            tops = np.stack([
                np.stack([x0, y0, top], -1), np.stack([x1, y0, top], -1),
                np.stack([x1, y1, top], -1), np.stack([x0, y1, top], -1)], axis=1)
            polys.append(tops)
            tcol = cmap(norm(top))
            faces.append(tcol)
            edges.append(np.tile(self.EDGE_COLOR, (n, 1)) if style.show_edges else tcol)

        # Боковые грани. Рисуется только часть, выступающая над соседним столбцом:
        # закрытые соседями участки не видны ни с какого ракурса, а их отсутствие
        # убирает ошибки сортировки граней и ускоряет отрисовку.
        if n:
            heights = np.zeros(values.shape)
            heights[rr, cc] = top - base
            padded = np.pad(heights, 1)
            segs = max(1, int(style.segments)) if style.gradient else 1
            t = np.linspace(0.0, 1.0, segs + 1)
            h = top - base
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            neighbours = [(-1, 0), (0, 1), (1, 0), (0, -1)]  # соседи за гранями в том же порядке
            for k in range(4):
                dr, dc = neighbours[k]
                hn = padded[rr + 1 + dr, cc + 1 + dc]
                with np.errstate(invalid="ignore", divide="ignore"):
                    start = np.where(h * hn > 0, np.clip(hn / h, 0.0, 1.0), 0.0)
                if not cull:
                    start = np.zeros_like(h)
                keep = start < 1.0 - 1e-9
                if not keep.any():
                    continue
                (ax_, ay_), (bx_, by_) = corners[k], corners[(k + 1) % 4]
                s, hk = start[keep], h[keep]
                z = base + hk[:, None] * (s[:, None] + (1.0 - s[:, None]) * t[None, :])
                za, zb = z[:, :-1], z[:, 1:]
                ax2, ay2 = (np.repeat(a[keep][:, None], segs, 1) for a in (ax_, ay_))
                bx2, by2 = (np.repeat(b[keep][:, None], segs, 1) for b in (bx_, by_))
                quad = np.stack([
                    np.stack([ax2, ay2, za], -1), np.stack([bx2, by2, za], -1),
                    np.stack([bx2, by2, zb], -1), np.stack([ax2, ay2, zb], -1)], axis=2)
                polys.append(quad.reshape(-1, 4, 3))
                if style.gradient:
                    col = cmap(norm(0.5 * (za + zb))).reshape(-1, 4)
                    edge = col
                else:
                    col = np.repeat(cmap(norm(top[keep])), segs, 0)
                    edge = np.tile(self.EDGE_COLOR, (len(col), 1)) if style.show_edges else col
                faces.append(col)
                edges.append(edge)

        # Плоская подложка: клетки вне эллипса и скрытые порогом.
        flat = (~bars) & (np.ones_like(mask) if style.show_base else mask)
        fr, fc = np.nonzero(flat)
        if fr.size:
            tw = float(np.clip(style.tile_width, 0.05, 1.0)) * block
            fx0 = data.col0 + fc * block + (block - tw) / 2.0
            fy0 = data.row0 + fr * block + (block - tw) / 2.0
            fz = np.full(fr.size, np.clip(base, norm.vmin, norm.vmax))
            tiles = np.stack([
                np.stack([fx0, fy0, fz], -1), np.stack([fx0 + tw, fy0, fz], -1),
                np.stack([fx0 + tw, fy0 + tw, fz], -1), np.stack([fx0, fy0 + tw, fz], -1)], axis=1)
            polys.append(tiles)
            col = cmap(norm(fz))
            faces.append(col)
            edges.append(np.tile((1.0, 1.0, 1.0, 1.0), (fr.size, 1)) if style.show_edges else col)

        if not polys:
            return np.empty((0, 4, 3)), np.empty((0, 4)), np.empty((0, 4))
        return np.concatenate(polys), np.concatenate(faces), np.concatenate(edges)

    @staticmethod
    def _setup_axes(ax, shape, data: RegionData, block: int, base: float,
                    vmin: float, vmax: float, inverted: bool, style: Bar3DStyle,
                    labels: AxisLabels) -> Tuple[float, float, float]:
        rows, cols = shape
        x_lo, x_hi = data.col0, data.col0 + cols * block
        y_lo, y_hi = data.row0, data.row0 + rows * block
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(y_hi, y_lo)  # строка 0 — «дальний» край, как на изображении
        z_lo, z_hi = min(base, vmin), max(base, vmax)
        if z_hi <= z_lo:
            z_hi = z_lo + 1e-3
        ax.set_zlim((z_hi, z_lo) if inverted else (z_lo, z_hi))

        span = float(max(x_hi - x_lo, y_hi - y_lo, 1))
        aspect = (x_hi - x_lo, y_hi - y_lo, max(1e-3, style.z_aspect) * span)
        try:
            ax.set_box_aspect(aspect, zoom=style.zoom)
        except TypeError:  # matplotlib < 3.6
            ax.set_box_aspect(aspect)
        try:
            ax.view_init(elev=style.elev, azim=style.azim, roll=style.roll)
        except TypeError:
            ax.view_init(elev=style.elev, azim=style.azim)

        if style.show_axes:
            ax.set_xlabel(pick(labels.x, DEFAULT_X_LABEL))
            ax.set_ylabel(pick(labels.y, DEFAULT_Y_LABEL))
            ax.set_zlabel(pick(labels.z, data.mode.unit_label))
        else:
            ax.set_axis_off()
        return aspect
