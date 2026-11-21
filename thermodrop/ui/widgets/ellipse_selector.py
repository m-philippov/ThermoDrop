"""Интерактивный эллипс выделения для pyqtgraph.

* значок ✥ в центре — перемещение;
* значок ⟳ за краем эллипса (на продолжении оси Rx) — поворот;
* перетаскивание самого эллипса — изменение размера (с Shift — пропорционально).

Координаты элемента совпадают с пиксельными координатами кадра.
"""

from __future__ import annotations

import math
from typing import Callable, Optional

import pyqtgraph as pg
from PyQt5.QtCore import QLineF, QObject, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PyQt5.QtWidgets import QGraphicsItem

from thermodrop.core.geometry import from_local, moved, resized, rotated
from thermodrop.core.models import EllipseRegion

HANDLE_RADIUS = 11.0  # в экранных пикселях
ROTATE_OFFSET = 2 * HANDLE_RADIUS + 6  # значок поворота вынесен за край эллипса, в пикселях
OUTLINE = QColor(20, 20, 30)
LIGHT = QColor(255, 255, 255)
ACCENT = QColor(255, 215, 0)


class _Signals(QObject):
    #: (EllipseRegion, final)
    region_edited = pyqtSignal(object, bool)


class _Handle(pg.GraphicsObject):
    """Значок постоянного экранного размера (не масштабируется вместе с изображением)."""

    def __init__(self, owner: "EllipseSelector", operation: Callable, painter: Callable,
                 cursor: Qt.CursorShape, tooltip: str) -> None:
        super().__init__(owner)
        self._owner = owner
        self._operation = operation
        self._draw_icon = painter
        self._hover = False
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setCursor(cursor)
        self.setToolTip(tooltip)
        self.setZValue(2)

    def boundingRect(self) -> QRectF:
        r = HANDLE_RADIUS + 2
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), HANDLE_RADIUS + 1, HANDLE_RADIUS + 1)
        return path

    def paint(self, p: QPainter, *args) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(OUTLINE, 1.5))
        p.setBrush(QBrush(ACCENT if self._hover else LIGHT))
        p.drawEllipse(QPointF(0, 0), HANDLE_RADIUS, HANDLE_RADIUS)
        self._draw_icon(p)

    def hoverEvent(self, ev) -> None:
        hover = (not ev.isExit()) and ev.acceptDrags(Qt.LeftButton)
        if hover != self._hover:
            self._hover = hover
            self.update()

    def mouseDragEvent(self, ev) -> None:
        self._owner.drag(ev, self._operation)


def _draw_move_icon(p: QPainter) -> None:
    p.setPen(QPen(OUTLINE, 1.6, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(QBrush(OUTLINE))
    s, h = 7.5, 2.8
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        tip = QPointF(dx * s, dy * s)
        p.drawLine(QLineF(QPointF(0, 0), tip))
        base = QPointF(dx * (s - h), dy * (s - h))
        side = QPointF(-dy * h * 0.8, dx * h * 0.8)
        p.drawPolygon(QPolygonF([tip, base + side, base - side]))


def _draw_rotate_icon(p: QPainter) -> None:
    p.setPen(QPen(OUTLINE, 1.8, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    r = 6.0
    p.drawArc(QRectF(-r, -r, 2 * r, 2 * r), 60 * 16, 270 * 16)
    # Наконечник в конце дуги (угол 330° по Qt, т. е. −30° против часовой).
    a = math.radians(-30.0)
    end = QPointF(r * math.cos(a), -r * math.sin(a))
    p.setBrush(QBrush(OUTLINE))
    tangent = QPointF(-math.sin(a), -math.cos(a))  # направление движения по дуге
    normal = QPointF(-tangent.y(), tangent.x())
    p.drawPolygon(QPolygonF([end + tangent * 3.5, end - normal * 3.2, end + normal * 3.2]))


class EllipseSelector(pg.GraphicsObject):
    def __init__(self, region: Optional[EllipseRegion] = None) -> None:
        super().__init__()
        self.signals = _Signals()
        self._region = region or EllipseRegion(10, 10, 5, 5)
        self._hover = False
        self._drag_start_region: Optional[EllipseRegion] = None
        self._drag_start_point = (0.0, 0.0)
        self._path = QPainterPath()
        self.setCursor(Qt.SizeFDiagCursor)
        self.setToolTip("Тяните эллипс — изменение размера (Shift — пропорционально)")
        self.setZValue(10)
        self._move = _Handle(self, moved, _draw_move_icon, Qt.SizeAllCursor, "Перемещение эллипса")
        self._rotate = _Handle(self, rotated, _draw_rotate_icon, Qt.OpenHandCursor, "Поворот эллипса")
        self._rebuild()

    # ------------------------------------------------------------------ состояние

    @property
    def region(self) -> EllipseRegion:
        return self._region

    def set_region(self, region: EllipseRegion) -> None:
        if region != self._region:
            self._region = region
            self._rebuild()

    def _rebuild(self) -> None:
        r = self._region
        self.prepareGeometryChange()
        base = QPainterPath()
        base.addEllipse(QPointF(0, 0), r.rx, r.ry)
        self._path = QTransform().translate(r.cx, r.cy).rotate(r.angle_deg).map(base)
        self._move.setPos(r.cx, r.cy)
        self._place_rotate_handle()
        self.update()

    def _place_rotate_handle(self) -> None:
        """Ставит значок поворота на фиксированном экранном расстоянии от края эллипса."""
        r = self._region
        a = math.radians(r.angle_deg)
        pixel = self.pixelLength(QPointF(math.cos(a), math.sin(a))) if self.getViewBox() else None
        offset = ROTATE_OFFSET * pixel if pixel else 0.0
        self._rotate.setPos(*from_local(r, (r.rx + offset, 0.0)))

    def viewTransformChanged(self) -> None:
        # Масштаб вида изменился — пересчитать вынос значка поворота.
        self.prepareGeometryChange()
        self._place_rotate_handle()
        self.update()

    # ------------------------------------------------------------------ QGraphicsItem

    def boundingRect(self) -> QRectF:
        handle = self._rotate.pos()
        return self._path.boundingRect().united(QRectF(handle, handle)).adjusted(-1, -1, 1, 1)

    def shape(self) -> QPainterPath:
        return self._path

    def paint(self, p: QPainter, *args) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        if self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, 40)))
            p.drawPath(self._path)
        p.setBrush(Qt.NoBrush)
        outer = QPen(OUTLINE, 4.0)
        outer.setCosmetic(True)
        inner = QPen(ACCENT if self._hover else LIGHT, 2.0)
        inner.setCosmetic(True)
        for pen in (outer, inner):
            p.setPen(pen)
            p.drawPath(self._path)
        # Ось Rx до значка поворота — чтобы был виден угол.
        r = self._region
        axis = QLineF(QPointF(r.cx, r.cy), self._rotate.pos())
        for color, width in ((OUTLINE, 3.0), (LIGHT, 1.2)):
            pen = QPen(color, width, Qt.DashLine if color == LIGHT else Qt.SolidLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawLine(axis)

    def hoverEvent(self, ev) -> None:
        hover = (not ev.isExit()) and ev.acceptDrags(Qt.LeftButton)
        if hover != self._hover:
            self._hover = hover
            self.update()

    def mouseDragEvent(self, ev) -> None:
        uniform = bool(ev.modifiers() & Qt.ShiftModifier)
        self.drag(ev, lambda reg, a, b: resized(reg, a, b, uniform=uniform))

    # ------------------------------------------------------------------ перетаскивание

    def drag(self, ev, operation: Callable) -> None:
        if ev.button() != Qt.LeftButton:
            ev.ignore()
            return
        ev.accept()
        current = self.mapFromScene(ev.scenePos())
        if ev.isStart():
            start = self.mapFromScene(ev.buttonDownScenePos())
            self._drag_start_region = self._region
            self._drag_start_point = (start.x(), start.y())
        if self._drag_start_region is None:
            return
        try:
            region = operation(self._drag_start_region, self._drag_start_point, (current.x(), current.y()))
        except ValueError:
            return
        self.set_region(region)
        finished = ev.isFinish()
        if finished:
            self._drag_start_region = None
        self.signals.region_edited.emit(region, finished)
