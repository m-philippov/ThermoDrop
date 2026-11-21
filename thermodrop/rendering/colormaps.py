"""Доступные цветовые шкалы."""

from __future__ import annotations

from typing import List

import numpy as np
from matplotlib import cm
from matplotlib.colors import Colormap

COLORMAPS: List[str] = ["jet", "turbo", "viridis", "plasma", "inferno", "magma",
                        "coolwarm", "RdYlBu_r", "hot", "gray"]
DEFAULT_COLORMAP = "jet"


def get_colormap(name: str) -> Colormap:
    try:
        import matplotlib
        return matplotlib.colormaps[name]
    except (AttributeError, KeyError):
        return cm.get_cmap(name if name in COLORMAPS else DEFAULT_COLORMAP)


def lookup_table(name: str, n: int = 256) -> np.ndarray:
    """Таблица RGBA 0..255 размером n×4 (для pyqtgraph)."""
    return (get_colormap(name)(np.linspace(0.0, 1.0, n)) * 255).astype(np.uint8)
