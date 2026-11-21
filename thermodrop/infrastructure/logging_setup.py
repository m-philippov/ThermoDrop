"""Настройка журналирования.

Записи идут одновременно в ротируемый файл и в окно логов приложения.
Необработанные исключения и сообщения Qt также попадают в журнал.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QObject, QtMsgType, pyqtSignal, qInstallMessageHandler

from thermodrop import __app_name__, __version__

FILE_FORMAT = "%(asctime)s.%(msecs)03d [%(levelname)-7s] %(name)s: %(message)s"
VIEW_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

log = logging.getLogger("thermodrop")


class LogBridge(QObject):
    """Передаёт записи журнала в GUI-поток через сигнал (потокобезопасно)."""

    record_emitted = pyqtSignal(int, str)  # уровень, текст


class QtLogHandler(logging.Handler):
    def __init__(self, bridge: LogBridge, level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self.bridge = bridge
        self.setFormatter(logging.Formatter(VIEW_FORMAT, "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.bridge.record_emitted.emit(record.levelno, self.format(record))
        except Exception:  # pragma: no cover — журнал не должен ронять приложение
            self.handleError(record)


def configure_logging(log_directory: Path, level: int = logging.DEBUG) -> Path:
    """Настраивает корневой логгер; возвращает путь к файлу журнала."""
    log_file = log_directory / ("%s.log" % __app_name__.lower())
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    if sys.stderr is not None:  # в сборке без консоли stderr отсутствует
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
        console.setLevel(logging.INFO)
        root.addHandler(console)

    for noisy in ("matplotlib", "PIL", "PyQt5"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    log.info("=" * 60)
    log.info("%s %s запущен; Python %s; журнал: %s", __app_name__, __version__,
             sys.version.split()[0], log_file)
    return log_file


def attach_view_handler(bridge: LogBridge) -> QtLogHandler:
    handler = QtLogHandler(bridge)
    logging.getLogger().addHandler(handler)
    return handler


def install_exception_hooks(on_error: Optional[Callable[[str], None]] = None) -> None:
    """Журналирует необработанные исключения (в т. ч. в потоках) и сообщения Qt."""

    def excepthook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Необработанное исключение", exc_info=(exc_type, exc, tb))
        if on_error is not None:
            try:
                on_error("%s: %s" % (exc_type.__name__, exc))
            except Exception:
                pass

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):
        def thread_hook(args):
            log.critical("Исключение в потоке %s", args.thread,
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        threading.excepthook = thread_hook

    qt_log = logging.getLogger("qt")
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def qt_handler(msg_type, context, message):
        qt_log.log(levels.get(msg_type, logging.INFO), "%s", message)

    qInstallMessageHandler(qt_handler)
