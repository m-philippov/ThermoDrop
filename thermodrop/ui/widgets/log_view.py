"""Окно журнала в нижней части главного окна."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices, QFont
from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from thermodrop.infrastructure.logging_setup import LogBridge

LEVELS = (("Отладка", logging.DEBUG), ("Инфо", logging.INFO), ("Предупр.", logging.WARNING),
          ("Ошибки", logging.ERROR))
COLORS = {logging.DEBUG: "#888888", logging.INFO: "#202020", logging.WARNING: "#b36b00",
          logging.ERROR: "#c00000", logging.CRITICAL: "#ff0000"}


class LogView(QWidget):
    MAX_LINES = 5000

    def __init__(self, bridge: LogBridge, log_file: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._log_file = log_file
        self._min_level = logging.INFO

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(self.MAX_LINES)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(9)
        self._text.setFont(font)

        self._level = QComboBox()
        for title, level in LEVELS:
            self._level.addItem(title, level)
        self._level.setCurrentIndex(1)
        self._level.currentIndexChanged.connect(self._on_level_changed)
        clear = QPushButton("Очистить")
        clear.clicked.connect(self._text.clear)
        open_dir = QPushButton("Папка журналов")
        open_dir.clicked.connect(self._open_folder)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Журнал"))
        bar.addStretch(1)
        bar.addWidget(QLabel("Уровень:"))
        bar.addWidget(self._level)
        bar.addWidget(clear)
        bar.addWidget(open_dir)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(bar)
        layout.addWidget(self._text, 1)

        bridge.record_emitted.connect(self._append)

    def _append(self, level: int, text: str) -> None:
        if level < self._min_level:
            return
        color = COLORS.get(level, "#202020")
        lines = html.escape(text).replace("\n", "<br>")
        self._text.appendHtml('<span style="color:%s">%s</span>' % (color, lines))

    def _on_level_changed(self, _index: int) -> None:
        self._min_level = self._level.currentData()
        logging.getLogger(__name__).info("Уровень окна журнала: %s", self._level.currentText())

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_file.parent)))
