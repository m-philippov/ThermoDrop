# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller packaging/thermodrop.spec  (из корня проекта)

import glob
import os
import struct

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ARCH = "x64" if struct.calcsize("P") == 8 else "x86"

hidden = [m for m in collect_submodules("pyqtgraph")
          if not any(x in m for x in (".opengl", ".jupyter", ".examples", "pyside", "pyqt6", ".canvas"))]
hidden += ["matplotlib.backends.backend_qt5agg", "matplotlib.backends.backend_agg",
           "matplotlib.backends.backend_svg", "matplotlib.backends.backend_pdf"]

# Universal CRT рядом с exe: на Windows 7 без обновления KB2999226 программа всё равно запустится.
ucrt = [(dll, ".") for dll in glob.glob(os.path.join(SPECPATH, "ucrt", ARCH, "*.dll"))]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=ucrt,
    datas=[(os.path.join(ROOT, "thermodrop", "resources"), os.path.join("thermodrop", "resources")),
           (os.path.join(ROOT, "doc", "*.pdf"), "doc")],  # руководство — в папке doc рядом с exe
    hiddenimports=hidden,
    excludes=["tkinter", "PySide2", "PySide6", "PyQt6", "IPython", "jupyter", "pytest",
              "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngineCore", "PyQt5.QtQml", "PyQt5.QtQuick",
              "PyQt5.QtMultimedia", "PyQt5.QtBluetooth", "PyQt5.QtSql", "OpenGL"],
    noarchive=False,
)
# Лишнее для программы (рисует без OpenGL, не использует QML): ~40 МБ.
UNUSED_BINARIES = ("opengl32sw.dll", "d3dcompiler_47.dll", "libegl.dll", "libglesv2.dll",
                   "qt5qml", "qt5quick", "qt5websockets")
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).lower().startswith(UNUSED_BINARIES)]
a.datas = [d for d in a.datas
           if "translations" not in d[0].replace("\\", "/") or os.path.basename(d[0]).endswith(("_ru.qm", "_en.qm"))]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ThermoDrop",
    icon=os.path.join(SPECPATH, "thermodrop.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ThermoDrop")
