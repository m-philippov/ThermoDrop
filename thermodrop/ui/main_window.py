"""Главное окно: компоновка панелей, меню и сценарии экспорта.

    ┌──────────────┬──────────────┐
    │ 1. Поле      │ 2. 3D        │
    ├──────────────┴──────────────┤
    │ 3. Гистограмма              │
    ├─────────────────────────────┤
    │ Журнал                      │
    └─────────────────────────────┘
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QRect, QSettings, Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QGroupBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from thermodrop import __app_name__, __version__
from thermodrop.fileio.readers import ReaderError, ReaderRegistry
from thermodrop.infrastructure.paths import guide_pdf, resources_dir
from thermodrop.rendering.bar3d import DEFAULT_X_LABEL, DEFAULT_Y_LABEL
from thermodrop.rendering.histogram import COUNT_LABEL
from thermodrop.services.export_service import IMAGE_FILTER, ExportService, ImageOptions
from thermodrop.services.session import AnalysisSession
from thermodrop.ui.dialogs.help_dialog import HelpDialog
from thermodrop.ui.dialogs.image_options_dialog import ImageOptionsDialog
from thermodrop.ui.widgets.bar3d_view import Bar3DView
from thermodrop.ui.widgets.field_view import FieldView
from thermodrop.ui.widgets.histogram_view import HistogramView
from thermodrop.ui.widgets.log_view import LogView

log = logging.getLogger(__name__)

CSV_FILTER = "CSV (*.csv);;Текст (*.txt)"


def _framed(title: str, widget: QWidget) -> QGroupBox:
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.addWidget(widget)
    return box


class MainWindow(QMainWindow):
    def __init__(self, session: AnalysisSession, readers: ReaderRegistry, exporter: ExportService,
                 field_view: FieldView, bar3d_view: Bar3DView, histogram_view: HistogramView,
                 log_view: LogView) -> None:
        super().__init__()
        self._session = session
        self._readers = readers
        self._exporter = exporter
        self._field_view = field_view
        self._bar3d_view = bar3d_view
        self._histogram_view = histogram_view
        self._settings = QSettings(__app_name__, __app_name__)
        self._bar3d_options = ImageOptions(width_px=1920, height_px=880, dpi=150)
        self._hist_options = ImageOptions(width_px=1600, height_px=500, dpi=150)

        self.setWindowTitle("%s %s" % (__app_name__, __version__))
        self.setAcceptDrops(True)

        self._top = QSplitter(Qt.Horizontal)
        self._top.addWidget(_framed("1. Температурное поле", field_view))
        self._top.addWidget(_framed("2. Трёхмерная диаграмма области", bar3d_view))
        self._top.setStretchFactor(0, 1)
        self._top.setStretchFactor(1, 1)

        self._main = QSplitter(Qt.Vertical)
        self._main.addWidget(self._top)
        self._main.addWidget(_framed("3. Гистограмма температур", histogram_view))
        self._main.addWidget(log_view)
        self._main.setStretchFactor(0, 6)
        self._main.setStretchFactor(1, 2)
        self._main.setStretchFactor(2, 1)
        self.setCentralWidget(self._main)

        self._file_label = QLabel("Файл не открыт")
        self.statusBar().addWidget(self._file_label, 1)

        self._build_menu()
        bar3d_view.export_requested.connect(self.export_bar3d_image)
        histogram_view.export_image_requested.connect(self.export_histogram_image)
        histogram_view.export_csv_requested.connect(self.export_histogram_csv)
        session.field_changed.connect(
            lambda f: self._file_label.setText("%s — %d×%d" % (f.source or "", f.rows, f.cols)))
        self._restore_state()

    # ------------------------------------------------------------------ меню

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&Файл")
        self._add_action(file_menu, "&Открыть…", self.open_dialog, QKeySequence.Open)
        file_menu.addSeparator()
        self._add_action(file_menu, "Экспорт 3D-изображения…", self.export_bar3d_image, "Ctrl+E")
        self._add_action(file_menu, "Экспорт гистограммы (изображение)…", self.export_histogram_image,
                         "Ctrl+Shift+E")
        self._add_action(file_menu, "Экспорт гистограммы (CSV)…", self.export_histogram_csv)
        self._add_action(file_menu, "Экспорт области: матрица (CSV)…", self.export_region_matrix)
        self._add_action(file_menu, "Экспорт области: список точек (CSV)…", self.export_region_points)
        file_menu.addSeparator()
        self._add_action(file_menu, "В&ыход", self.close, "Ctrl+Q")

        help_menu = self.menuBar().addMenu("&Справка")
        self._add_action(help_menu, "Руководство пользователя", self.show_guide, QKeySequence.HelpContents)
        self._add_action(help_menu, "Открыть руководство в PDF", self._open_guide_pdf)
        help_menu.addSeparator()
        self._add_action(help_menu, "О программе", self._about)

    def _add_action(self, menu, title: str, slot: Callable, shortcut=None) -> QAction:
        action = QAction(title, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _=False: slot())
        menu.addAction(action)
        return action

    # ------------------------------------------------------------------ открытие

    def open_dialog(self) -> None:
        start = self._settings.value("last_dir", "", type=str)
        path, _ = QFileDialog.getOpenFileName(self, "Открыть кадр", start, self._readers.file_filter())
        if path:
            self.open_path(Path(path))
        else:
            log.debug("Открытие файла отменено")

    def open_path(self, path: Path) -> None:
        try:
            self._session.open_file(path)
        except (ReaderError, OSError, ValueError) as exc:
            log.error("Не удалось открыть %s: %s", path, exc)
            QMessageBox.critical(self, "Ошибка открытия", "Не удалось открыть файл:\n%s\n\n%s" % (path, exc))
            return
        except Exception:
            log.exception("Непредвиденная ошибка при открытии %s", path)
            QMessageBox.critical(self, "Ошибка открытия", "Непредвиденная ошибка, подробности в журнале.")
            return
        self._settings.setValue("last_dir", str(path.parent))
        self.setWindowTitle("%s — %s" % (path.name, __app_name__))

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = [u for u in event.mimeData().urls() if u.isLocalFile()]
        if urls:
            path = Path(urls[0].toLocalFile())
            log.info("Файл перетащен в окно: %s", path)
            self.open_path(path)

    # ------------------------------------------------------------------ экспорт

    def _ask_save_path(self, caption: str, file_filter: str, default_name: str) -> Optional[Path]:
        start = self._settings.value("export_dir", "", type=str) or self._settings.value("last_dir", "", type=str)
        path, _ = QFileDialog.getSaveFileName(self, caption, str(Path(start) / default_name), file_filter)
        if not path:
            log.debug("Экспорт отменён: %s", caption)
            return None
        self._settings.setValue("export_dir", str(Path(path).parent))
        return Path(path)

    def _base_name(self) -> str:
        field = self._session.field
        return field.source.stem if field and field.source else "thermodrop"

    def _run_export(self, title: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:
            log.exception("Ошибка экспорта (%s)", title)
            QMessageBox.critical(self, "Ошибка экспорта", "%s:\n%s" % (title, exc))
            return
        self.statusBar().showMessage("Сохранено: %s" % title, 5000)

    def _require_region(self) -> bool:
        if self._session.region_data is None or self._session.region_data.is_empty:
            log.warning("Нет данных для экспорта: откройте файл и выделите область")
            QMessageBox.information(self, __app_name__, "Сначала откройте файл и выделите область.")
            return False
        return True

    def export_bar3d_image(self) -> None:
        if not self._require_region():
            return
        unit = self._session.value_mode.unit_label
        fields = (("x", "Ось X:", DEFAULT_X_LABEL), ("y", "Ось Y:", DEFAULT_Y_LABEL),
                  ("z", "Ось Z:", unit), ("colorbar", "Цветовая шкала:", unit))
        dialog = ImageOptionsDialog("Параметры 3D-изображения", self._bar3d_options, fields,
                                    show_axes=self._bar3d_view.style.show_axes, parent=self)
        if dialog.exec_() != ImageOptionsDialog.Accepted:
            return
        self._bar3d_options = dialog.options()
        path = self._ask_save_path("Сохранить 3D-изображение", IMAGE_FILTER, self._base_name() + "_3d.png")
        if path:
            self._run_export(path.name, lambda: self._exporter.export_bar3d(
                path, self._session.region_data, self._bar3d_view.style,
                self._session.threshold, self._bar3d_options))

    def export_histogram_image(self) -> None:
        hist = self._session.histogram()
        if hist is None or not self._require_region():
            return
        unit = self._session.value_mode.unit_label
        vertical = self._histogram_view.style.values_vertical
        fields = (("x", "Ось X:", COUNT_LABEL if vertical else unit),
                  ("y", "Ось Y:", unit if vertical else COUNT_LABEL))
        dialog = ImageOptionsDialog("Параметры изображения гистограммы", self._hist_options, fields,
                                    parent=self)
        if dialog.exec_() != ImageOptionsDialog.Accepted:
            return
        self._hist_options = dialog.options()
        path = self._ask_save_path("Сохранить гистограмму", IMAGE_FILTER, self._base_name() + "_hist.png")
        if path:
            self._run_export(path.name, lambda: self._exporter.export_histogram_image(
                path, hist, self._histogram_view.style, self._session.value_mode.unit_label,
                self._hist_options))

    def export_histogram_csv(self) -> None:
        hist = self._session.histogram()
        if hist is None or not self._require_region():
            return
        path = self._ask_save_path("Сохранить гистограмму (CSV)", CSV_FILTER, self._base_name() + "_hist.csv")
        if path:
            self._run_export(path.name, lambda: self._exporter.export_histogram_csv(
                path, hist, self._session.value_mode.unit_label))

    def export_region_matrix(self) -> None:
        if not self._require_region():
            return
        path = self._ask_save_path("Сохранить матрицу области", CSV_FILTER, self._base_name() + "_region.csv")
        if path:
            self._run_export(path.name, lambda: self._exporter.export_region_matrix(path, self._session.region_data))

    def export_region_points(self) -> None:
        if not self._require_region():
            return
        path = self._ask_save_path("Сохранить точки области", CSV_FILTER, self._base_name() + "_points.csv")
        if path:
            self._run_export(path.name, lambda: self._exporter.export_region_points(path, self._session.region_data))

    # ------------------------------------------------------------------ прочее

    def show_guide(self) -> None:
        log.info("Открыто руководство пользователя")
        HelpDialog(resources_dir() / "guide", guide_pdf(), self).exec_()

    def _open_guide_pdf(self) -> None:
        pdf = guide_pdf()
        log.info("Открытие PDF-руководства: %s", pdf)
        if not pdf.exists() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf))):
            log.warning("PDF-руководство не открылось — показываю встроенное")
            self.show_guide()

    def _about(self) -> None:
        log.info("Открыто окно «О программе»")
        QMessageBox.about(
            self, "О программе",
            "<b>%s %s</b><br>Анализ температурных полей висящей капли.<br><br>"
            "1 — поле и эллипс выделения; 2 — 3D-диаграмма области "
            "(мышь: вращение, колесо — масштаб, Ctrl/Shift+колесо — шкала);<br>"
            "3 — гистограмма с линией порога; внизу — журнал.<br><br>"
            "Подробно — в меню «Справка → Руководство пользователя» (F1)." % (__app_name__, __version__))

    def _restore_state(self) -> None:
        geometry = self._settings.value("geometry")
        if geometry is None or not self.restoreGeometry(geometry) or not self._is_on_screen():
            # Нет сохранённой геометрии или окно оказалось вне экранов (например, отключён монитор).
            self.setGeometry(self._default_geometry())
        for key, splitter in (("split_top", self._top), ("split_main", self._main)):
            state = self._settings.value(key)
            if state is not None:
                splitter.restoreState(state)

    def _is_on_screen(self) -> bool:
        frame = self.frameGeometry()
        for screen in QApplication.screens():
            visible = screen.availableGeometry().intersected(frame)
            if visible.width() >= 200 and visible.height() >= 150:
                return True
        return False

    @staticmethod
    def _default_geometry() -> QRect:
        area = QApplication.primaryScreen().availableGeometry()
        width, height = min(1500, area.width() - 40), min(1000, area.height() - 60)
        rect = QRect(0, 0, width, height)
        rect.moveCenter(area.center())
        return rect

    def closeEvent(self, event) -> None:
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("split_top", self._top.saveState())
        self._settings.setValue("split_main", self._main.saveState())
        log.info("Приложение закрыто")
        super().closeEvent(event)
