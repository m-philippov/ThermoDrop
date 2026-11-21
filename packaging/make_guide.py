"""Собирает PDF руководства пользователя из thermodrop/resources/guide/guide.html.

Запуск (из корня проекта): python packaging/make_guide.py [--preview ПАПКА]
Результат: doc/Руководство ThermoDrop.pdf
С --preview страницы дополнительно сохраняются как PNG — для проверки вёрстки.
"""

import argparse
import sys
from pathlib import Path

from PyQt5.QtCore import QMarginsF, QRectF, QSizeF, QUrl
from PyQt5.QtGui import QImage, QPageLayout, QPageSize, QPainter, QTextDocument
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
GUIDE_DIR = ROOT / "thermodrop" / "resources" / "guide"
OUTPUT = ROOT / "doc" / "Руководство ThermoDrop.pdf"


def build_document() -> QTextDocument:
    doc = QTextDocument()
    doc.setBaseUrl(QUrl.fromLocalFile(str(GUIDE_DIR) + "/"))
    # Картинки загружаются явно: QTextDocument вне QTextBrowser не всегда сам находит файлы.
    for image in (GUIDE_DIR / "img").glob("*.png"):
        doc.addResource(QTextDocument.ImageResource, QUrl("img/" + image.name), QImage(str(image)))
    doc.setHtml((GUIDE_DIR / "guide.html").read_text(encoding="utf-8"))
    return doc


def save_preview(doc: QTextDocument, printer: QPrinter, folder: Path) -> None:
    """Те же страницы, что и в PDF, в виде PNG (раскладка по размеру страницы принтера)."""
    folder.mkdir(parents=True, exist_ok=True)
    # QTextDocument.print_ раскладывает страницу в экранных пикселях (96 dpi) — повторяем это.
    points = printer.pageLayout().paintRectPoints()
    page = QRectF(0, 0, points.width() * 96 / 72, points.height() * 96 / 72)
    scale = 1.2
    doc = doc.clone()
    doc.setPageSize(QSizeF(page.width(), page.height()))
    for i in range(doc.pageCount()):
        img = QImage(int(page.width() * scale), int(page.height() * scale), QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        p = QPainter(img)
        p.scale(scale, scale)
        p.translate(0, -i * page.height())
        doc.drawContents(p, QRectF(0, i * page.height(), page.width(), page.height()))
        p.end()
        img.save(str(folder / ("page_%02d.png" % (i + 1))))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()

    app = QApplication(sys.argv[:1])  # нужен для шрифтов и картинок
    doc = build_document()

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(OUTPUT))
    printer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                      QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter))
    printer.setDocName("ThermoDrop — руководство пользователя")
    printer.setCreator("ThermoDrop")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.print_(printer)
    print("PDF:", OUTPUT)
    if args.preview:
        save_preview(doc, printer, args.preview)
        print("Страниц:", doc.pageCount(), "предпросмотр:", args.preview)
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
