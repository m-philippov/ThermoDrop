"""Точка сборки приложения (composition root): создаёт и связывает все объекты."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List, Optional

from thermodrop import __app_name__


def run(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # Импорты Qt — после разбора аргументов, чтобы ошибки окружения попали в журнал.
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QMessageBox

    from thermodrop.infrastructure.logging_setup import (
        LogBridge,
        attach_view_handler,
        configure_logging,
        install_exception_hooks,
    )
    from thermodrop.infrastructure.paths import log_dir

    log_file = configure_logging(log_dir())
    log = logging.getLogger("thermodrop")

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName(__app_name__)
    # Русские надписи стандартных кнопок Qt («Отмена», «Да» и т. п.).
    from PyQt5.QtCore import QLibraryInfo, QLocale, QTranslator
    translator = QTranslator(app)
    if translator.load(QLocale("ru_RU"), "qtbase", "_", QLibraryInfo.location(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
    else:
        log.debug("Перевод Qt на русский не найден")
    icon_path = Path(__file__).resolve().parent / "resources" / "thermodrop.ico"
    if icon_path.exists():
        from PyQt5.QtGui import QIcon
        app.setWindowIcon(QIcon(str(icon_path)))

    bridge = LogBridge()
    attach_view_handler(bridge)

    def show_error(text: str) -> None:
        QMessageBox.critical(None, "Ошибка", "%s\n\nПодробности — в журнале:\n%s" % (text, log_file))

    install_exception_hooks(show_error)

    import matplotlib
    matplotlib.use("Qt5Agg")
    import pyqtgraph as pg

    pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)

    from thermodrop.fileio.readers import default_registry
    from thermodrop.rendering.bar3d import Bar3DRenderer
    from thermodrop.rendering.histogram import HistogramRenderer
    from thermodrop.services.export_service import ExportService
    from thermodrop.services.session import AnalysisSession
    from thermodrop.ui.main_window import MainWindow
    from thermodrop.ui.widgets.bar3d_view import Bar3DView
    from thermodrop.ui.widgets.field_view import FieldView
    from thermodrop.ui.widgets.histogram_view import HistogramView
    from thermodrop.ui.widgets.log_view import LogView

    readers = default_registry()
    bar3d_renderer = Bar3DRenderer()
    histogram_renderer = HistogramRenderer()
    session = AnalysisSession(readers)

    window = MainWindow(
        session=session,
        readers=readers,
        exporter=ExportService(bar3d_renderer, histogram_renderer),
        field_view=FieldView(session),
        bar3d_view=Bar3DView(session, bar3d_renderer),
        histogram_view=HistogramView(session, histogram_renderer),
        log_view=LogView(bridge, log_file),
    )
    window.show()
    log.info("Главное окно открыто")

    files = [Path(a) for a in argv[1:] if not a.startswith("-")]
    if files:
        window.open_path(files[0])

    code = app.exec_()
    log.info("Выход с кодом %d", code)
    return code
