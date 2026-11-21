"""Чтение температурных полей из файлов.

Поддерживаемый формат (экспорт тепловизора в CSV/TXT)::

    320;240                      <- необязательный заголовок: строк;столбцов
    18,7;18,5;18,6;...           <- значения, разделитель ; / Tab / пробел / ,
    ...

Десятичный разделитель — запятая или точка.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import numpy as np

from thermodrop.core.models import ThermalField

log = logging.getLogger(__name__)


class ReaderError(Exception):
    """Файл не удалось прочитать как температурное поле."""


class FieldReader(ABC):
    """Интерфейс читателя кадра."""

    #: Расширения файлов (в нижнем регистре, с точкой).
    extensions: Sequence[str] = ()
    #: Название формата для диалога открытия файла.
    description: str = ""

    def can_read(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    @abstractmethod
    def read(self, path: Path) -> ThermalField:
        raise NotImplementedError


class DelimitedTextReader(FieldReader):
    """Текстовая таблица с автоопределением разделителя и десятичного знака."""

    extensions = (".csv", ".txt", ".dat", ".tsv")
    description = "Таблицы температур (*.csv *.txt *.dat *.tsv)"

    _ENCODINGS = ("utf-8-sig", "cp1251", "latin-1")

    def read(self, path: Path) -> ThermalField:
        log.debug("Чтение файла %s", path)
        text = self._decode(path.read_bytes())
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            raise ReaderError("Файл пуст")

        delimiter = self._detect_delimiter(lines[min(1, len(lines) - 1)])
        decimal_comma = delimiter != "," and "," in lines[min(1, len(lines) - 1)]
        log.debug("Разделитель=%r, десятичная запятая=%s", delimiter, decimal_comma)

        header = self._parse_header(lines[0], delimiter)
        body = lines[1:] if header else lines
        rows = [self._parse_row(ln, delimiter, decimal_comma, i + (2 if header else 1))
                for i, ln in enumerate(body)]
        data = self._to_matrix(rows)

        if header and tuple(header) != data.shape:
            log.warning("Размер из заголовка %s не совпадает с фактическим %s — используется фактический",
                        tuple(header), data.shape)
        n_bad = int((~np.isfinite(data)).sum())
        if n_bad:
            log.warning("В файле %d нечисловых/пропущенных значений (заменены на NaN)", n_bad)
        log.info("Прочитан кадр %s: %d×%d (строк×столбцов), T = %.2f…%.2f °C",
                 path.name, data.shape[0], data.shape[1], np.nanmin(data), np.nanmax(data))
        return ThermalField(data=data, source=path)

    def _decode(self, raw: bytes) -> str:
        for enc in self._ENCODINGS:
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        raise ReaderError("Не удалось определить кодировку файла")

    @staticmethod
    def _detect_delimiter(sample: str) -> Optional[str]:
        for candidate in ("\t", ";"):
            if candidate in sample:
                return candidate
        # Запятая — разделитель полей, только если в строке нет «десятичных запятых»
        # вида 18,7;... (тогда выше сработал бы ';').
        if "," in sample and " " not in sample.strip() and "." in sample:
            return ","
        return None  # произвольные пробелы

    @staticmethod
    def _split(line: str, delimiter: Optional[str]) -> List[str]:
        parts = line.split(delimiter) if delimiter else re.split(r"\s+", line)
        while parts and parts[-1].strip() == "":
            parts.pop()
        return parts

    def _parse_header(self, line: str, delimiter: Optional[str]) -> Optional[List[int]]:
        parts = [p.strip() for p in self._split(line, delimiter)]
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            return [int(parts[0]), int(parts[1])]
        return None

    def _parse_row(self, line: str, delimiter: Optional[str], decimal_comma: bool, line_no: int) -> List[float]:
        values = []
        for token in self._split(line, delimiter):
            token = token.strip()
            if decimal_comma:
                token = token.replace(",", ".")
            try:
                values.append(float(token))
            except ValueError:
                if token:
                    log.debug("Строка %d: нечисловое значение %r", line_no, token)
                values.append(float("nan"))
        return values

    @staticmethod
    def _to_matrix(rows: List[List[float]]) -> np.ndarray:
        if not rows:
            raise ReaderError("В файле нет данных")
        width = max(len(r) for r in rows)
        if width == 0:
            raise ReaderError("В файле нет данных")
        ragged = sum(1 for r in rows if len(r) != width)
        if ragged:
            log.warning("%d строк короче остальных — дополнены NaN", ragged)
        data = np.full((len(rows), width), np.nan)
        for i, r in enumerate(rows):
            data[i, :len(r)] = r
        return data


class ReaderRegistry:
    """Реестр читателей (фабрика по расширению файла)."""

    def __init__(self, readers: Iterable[FieldReader] = ()) -> None:
        self._readers: List[FieldReader] = list(readers)

    def register(self, reader: FieldReader) -> None:
        self._readers.append(reader)

    def reader_for(self, path: Path) -> FieldReader:
        for reader in self._readers:
            if reader.can_read(path):
                return reader
        raise ReaderError("Формат файла «%s» не поддерживается" % path.suffix)

    def read(self, path: Path) -> ThermalField:
        return self.reader_for(path).read(path)

    def file_filter(self) -> str:
        """Строка фильтра для QFileDialog."""
        items = [r.description for r in self._readers if r.description]
        items.append("Все файлы (*.*)")
        return ";;".join(items)


def default_registry() -> ReaderRegistry:
    return ReaderRegistry([DelimitedTextReader()])
