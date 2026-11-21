"""Пути к каталогам приложения."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from thermodrop import __app_name__


def user_data_dir() -> Path:
    """%LOCALAPPDATA%\\ThermoDrop (Windows) или ~/.thermodrop."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    path = Path(base) / __app_name__ if base else Path.home() / (".%s" % __app_name__.lower())
    path.mkdir(parents=True, exist_ok=True)
    return path


def install_dir() -> Path:
    """Папка программы: рядом с exe в сборке или корень проекта при запуске из исходников."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resources_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "resources"


def guide_pdf() -> Path:
    return install_dir() / "doc" / "Руководство ThermoDrop.pdf"


def log_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
