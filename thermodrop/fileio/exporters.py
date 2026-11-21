"""Экспорт данных в CSV (разделитель «;», десятичная запятая — для Excel в русской локали)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List

import numpy as np

from thermodrop.core.models import HistogramResult, RegionData

log = logging.getLogger(__name__)

SEP = ";"


def _fmt(value: float, digits: int = 3) -> str:
    if value is None or not np.isfinite(value):
        return ""
    return ("%.*f" % (digits, value)).replace(".", ",")


def _write(path: Path, lines: Iterable[str]) -> None:
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8-sig")


def export_region_matrix(path: Path, region: RegionData) -> None:
    """Матрица значений области; вне эллипса — пустые ячейки."""
    values = np.where(region.mask, region.values, np.nan)
    lines: List[str] = [
        "# Режим" + SEP + region.mode.unit_label,
        "# Опорная температура, °C" + SEP + _fmt(region.reference),
        "# Смещение (строка; столбец)" + SEP + str(region.row0) + SEP + str(region.col0),
        "%d%s%d" % (values.shape[0], SEP, values.shape[1]),
    ]
    lines += [SEP.join(_fmt(v, 2) for v in row) for row in values]
    _write(path, lines)
    log.info("Экспортирована матрица области (%d×%d) в %s", values.shape[0], values.shape[1], path)


def export_region_points(path: Path, region: RegionData) -> None:
    """Список точек внутри эллипса: строка; столбец; значение."""
    rr, cc = np.nonzero(region.mask)
    lines = ["Строка" + SEP + "Столбец" + SEP + region.mode.unit_label]
    for r, c in zip(rr, cc):
        lines.append(SEP.join((str(r + region.row0), str(c + region.col0), _fmt(region.values[r, c], 2))))
    _write(path, lines)
    log.info("Экспортировано %d точек области в %s", len(rr), path)


def export_histogram(path: Path, hist: HistogramResult, unit_label: str) -> None:
    s = hist.selected
    lines = [
        "# Фильтр" + SEP + hist.filter.title + SEP + "порог" + SEP + _fmt(hist.threshold),
        "# N" + SEP + str(s.count) + SEP + "доля" + SEP + _fmt(hist.fraction_selected, 4),
        "# Мин" + SEP + _fmt(s.minimum) + SEP + "Макс" + SEP + _fmt(s.maximum),
        "# Среднее" + SEP + _fmt(s.mean) + SEP + "Медиана" + SEP + _fmt(s.median) + SEP + "СКО" + SEP + _fmt(s.std),
        SEP.join(("От, " + unit_label, "До, " + unit_label, "Центр", "Количество")),
    ]
    for lo, hi, c, n in zip(hist.edges[:-1], hist.edges[1:], hist.centers, hist.counts):
        lines.append(SEP.join((_fmt(lo), _fmt(hi), _fmt(c), str(int(n)))))
    _write(path, lines)
    log.info("Экспортирована гистограмма (%d интервалов) в %s", len(hist.counts), path)
