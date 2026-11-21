"""Общие помощники для виджетов."""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from typing import Iterable, Iterator, Type

from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


@contextmanager
def signals_blocked(*objects: QObject) -> Iterator[None]:
    previous = [o.blockSignals(True) for o in objects]
    try:
        yield
    finally:
        for o, p in zip(objects, previous):
            o.blockSignals(p)


def double_spin(minimum: float, maximum: float, step: float = 1.0, decimals: int = 2,
                suffix: str = "", tooltip: str = "") -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setKeyboardTracking(False)
    spin.setAccelerated(True)
    if suffix:
        spin.setSuffix(suffix)
    if tooltip:
        spin.setToolTip(tooltip)
    return spin


def int_spin(minimum: int, maximum: int, step: int = 1, tooltip: str = "",
             special: str = "") -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setKeyboardTracking(False)
    if tooltip:
        spin.setToolTip(tooltip)
    if special:
        spin.setSpecialValueText(special)
    return spin


def enum_combo(enum_type: Type[Enum], items: Iterable[Enum] = ()) -> QComboBox:
    """Выпадающий список элементов перечисления (у элементов должно быть свойство ``title``)."""
    combo = QComboBox()
    for item in (list(items) or list(enum_type)):
        combo.addItem(item.title, item)
    return combo


def select_data(combo: QComboBox, value: object) -> None:
    index = combo.findData(value)
    if index >= 0:
        with signals_blocked(combo):
            combo.setCurrentIndex(index)


class Debouncer(QObject):
    """Откладывает вызов до паузы в событиях (для тяжёлых перерисовок)."""

    def __init__(self, delay_ms: int, callback, parent: QObject = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(callback)

    def trigger(self) -> None:
        self._timer.start()

    def flush(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._timer.timeout.emit()
