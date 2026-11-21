"""Гистограмма температур с линией порога."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

import numpy as np
from matplotlib.colors import Normalize
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from thermodrop.core.models import HistogramFilter, HistogramResult
from thermodrop.rendering.colormaps import DEFAULT_COLORMAP, get_colormap
from thermodrop.rendering.labels import AxisLabels, pick


@dataclass(frozen=True)
class HistogramStyle:
    #: True — температура по вертикали, порог — горизонтальная линия.
    values_vertical: bool = False
    cmap: str = DEFAULT_COLORMAP
    colored: bool = True
    show_ghost: bool = True
    show_stats: bool = False
    log_scale: bool = False

    def with_(self, **changes) -> "HistogramStyle":
        return replace(self, **changes)


@dataclass
class HistogramArtists:
    ax: object
    threshold_line: Line2D


COUNT_LABEL = "Количество"


class HistogramRenderer:
    GHOST_COLOR = (0.82, 0.82, 0.82, 1.0)
    PLAIN_COLOR = (0.18, 0.40, 0.75, 1.0)
    LINE_COLOR = "#d62728"

    def render(self, fig: Figure, hist: Optional[HistogramResult], style: HistogramStyle,
               unit_label: str, compact: bool = True,
               labels: AxisLabels = AxisLabels()) -> Optional[HistogramArtists]:
        fig.clear()
        fig.set_facecolor("white")
        if hist is None:
            fig.text(0.5, 0.5, "Нет данных", ha="center", va="center", color="0.4")
            return None

        ax = fig.add_subplot(111)
        widths = np.diff(hist.edges)
        lefts = hist.edges[:-1]
        if style.colored:
            norm = Normalize(vmin=hist.edges[0], vmax=hist.edges[-1])
            colors = get_colormap(style.cmap)(norm(hist.centers))
        else:
            colors = self.PLAIN_COLOR

        bar = ax.barh if style.values_vertical else ax.bar
        size_kw = "height" if style.values_vertical else "width"
        common = {size_kw: widths, "align": "edge", "linewidth": 0.3, "edgecolor": "0.3"}
        if style.show_ghost and hist.filter is not HistogramFilter.ALL:
            bar(lefts, hist.counts_all, color=self.GHOST_COLOR, **common)
        bar(lefts, hist.counts, color=colors, **common)

        if style.values_vertical:
            line = ax.axhline(hist.threshold, color=self.LINE_COLOR, linewidth=1.6, picker=5)
            ax.set_ylabel(pick(labels.y, unit_label))
            ax.set_xlabel(pick(labels.x, COUNT_LABEL))
            ax.set_ylim(hist.edges[0], hist.edges[-1])
            if style.log_scale:
                ax.set_xscale("symlog")
        else:
            line = ax.axvline(hist.threshold, color=self.LINE_COLOR, linewidth=1.6, picker=5)
            ax.set_xlabel(pick(labels.x, unit_label))
            ax.set_ylabel(pick(labels.y, COUNT_LABEL))
            ax.set_xlim(hist.edges[0], hist.edges[-1])
            if style.log_scale:
                ax.set_yscale("symlog")
        ax.grid(True, alpha=0.3, linewidth=0.5)

        if style.show_stats:
            s = hist.selected
            ax.text(0.99, 0.97,
                    "%s, порог %.2f\nN = %d (%.1f%%)\nсреднее %.2f, СКО %.2f\nмин %.2f, макс %.2f" % (
                        hist.filter.title, hist.threshold, s.count, 100 * hist.fraction_selected,
                        s.mean, s.std, s.minimum, s.maximum),
                    transform=ax.transAxes, ha="right", va="top", fontsize=8,
                    bbox=dict(boxstyle="round", fc="white", ec="0.7", alpha=0.85))
        if compact:
            ax.tick_params(labelsize=8)
            ax.xaxis.label.set_size(8)
            ax.yaxis.label.set_size(8)
        try:
            fig.tight_layout(pad=0.4)
        except Exception:  # слишком маленькое окно — не критично
            pass
        return HistogramArtists(ax=ax, threshold_line=line)
