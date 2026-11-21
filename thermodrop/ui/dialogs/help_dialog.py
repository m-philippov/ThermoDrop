"""Окно руководства пользователя.

Руководство показывается прямо в программе (HTML), поэтому работает и там, где нет
программы для просмотра PDF. Кнопки позволяют открыть или сохранить PDF-версию.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


class HelpDialog(QDialog):
    def __init__(self, guide_dir: Path, pdf: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pdf = pdf
        self.setWindowTitle("Руководство пользователя — ThermoDrop")
        self.resize(900, 760)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setSearchPaths([str(guide_dir)])
        self._browser.setSource(QUrl.fromLocalFile(str(guide_dir / "guide.html")))

        open_pdf = QPushButton("Открыть PDF")
        open_pdf.clicked.connect(self._open_pdf)
        save_pdf = QPushButton("Сохранить PDF как…")
        save_pdf.clicked.connect(self._save_pdf)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        for button in (open_pdf, save_pdf):
            button.setEnabled(pdf.exists())

        buttons = QHBoxLayout()
        buttons.addWidget(open_pdf)
        buttons.addWidget(save_pdf)
        buttons.addStretch(1)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(self._browser, 1)
        layout.addLayout(buttons)

    def _open_pdf(self) -> None:
        log.info("Открытие PDF-руководства: %s", self._pdf)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._pdf))):
            log.warning("Не удалось открыть PDF: нет программы для просмотра PDF")
            QMessageBox.information(
                self, "PDF", "На компьютере нет программы для просмотра PDF.\n"
                "Руководство можно читать в этом окне или сохранить PDF и открыть на другом компьютере.\n\n"
                "Файл: %s" % self._pdf)

    def _save_pdf(self) -> None:
        target, _ = QFileDialog.getSaveFileName(self, "Сохранить руководство",
                                                str(Path.home() / self._pdf.name), "PDF (*.pdf)")
        if not target:
            return
        try:
            shutil.copyfile(str(self._pdf), target)
        except OSError as exc:
            log.error("Не удалось сохранить руководство в %s: %s", target, exc)
            QMessageBox.critical(self, "Ошибка", "Не удалось сохранить файл:\n%s" % exc)
            return
        log.info("Руководство сохранено: %s", target)
