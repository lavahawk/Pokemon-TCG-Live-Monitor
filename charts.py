"""
Interactive line charts for the dashboard (pure Qt, no matplotlib).

SeriesChart draws one series of points spaced evenly by index (game /
rank update), so long breaks between sessions don't squash the data into a
corner. Days are marked with faint separators and labelled underneath; labels
that would collide are skipped, so axis text never overlaps.

Interaction:
- hover: crosshair snaps to the nearest point and shows a tooltip
- drag: zoom into the selected stretch
- double-click / right-click: back to the default (auto) view
- wheel: scrolls the page, like the rest of the dashboard
"""

import math
from datetime import datetime

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QLinearGradient, QFont, QFontMetrics, QFontDatabase
from PySide6.QtWidgets import QWidget, QScrollArea, QSizePolicy


TEXT = QColor(226, 235, 246, 150)
TEXT_STRONG = QColor(244, 249, 255, 235)
GRID = QColor(255, 255, 255, 16)
DAY_LINE = QColor(255, 255, 255, 26)


_chart_family = None


def chart_font():
    """The font the old matplotlib graphs used (DejaVu Sans, 8 pt at 90 dpi),
    loaded from matplotlib's bundled copy; the app font if that's missing."""
    global _chart_family
    if _chart_family is None:
        _chart_family = ""
        try:
            import os
            import matplotlib
            path = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
            families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(path))
            _chart_family = families[0] if families else ""
        except Exception:
            _chart_family = ""
    font = QFont(_chart_family) if _chart_family else QFont()
    font.setPixelSize(10)
    return font


def nice_step(span, max_ticks):
    """A 1/2/2.5/5 x 10^n step giving at most `max_ticks` intervals."""
    raw = max(span, 1e-9) / max(1, max_ticks)
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if mult * mag >= raw:
            return mult * mag
    return 10 * mag


def auto_y_range(values, max_ticks, min_pad=1.0, include=(), clamp=None):
    """(lo, hi, step) fitted to the values, snapped to tick multiples."""
    vals = [v for v in values if v is not None] + list(include)
    if not vals:
        return 0.0, 1.0, 0.5
    lo, hi = min(vals), max(vals)
    pad = max((hi - lo) * 0.12, min_pad)
    lo, hi = lo - pad, hi + pad
    if clamp:
        lo, hi = max(lo, clamp[0]), min(hi, clamp[1])
    step = nice_step(hi - lo, max_ticks)
    lo = math.floor(lo / step + 1e-9) * step
    hi = math.ceil(hi / step - 1e-9) * step
    if clamp:
        lo, hi = max(lo, clamp[0]), min(hi, clamp[1])
    if hi <= lo:
        hi = lo + step
    return lo, hi, step


def _fmt_day(value):
    return f"{value:%b} {value.day}"


def _fmt_time(value):
    hour = value.hour % 12 or 12
    return f"{hour}:{value:%M} {'AM' if value.hour < 12 else 'PM'}"


class SeriesChart(QWidget):
    """Index-spaced line chart with hover tooltips and drag-to-zoom.

    set_data(points, auto_view) where each point is a dict:
        y      float (required)
        t      datetime (for the day axis)
        dot    colour of the marker (None = accent)
        tip    list of tooltip lines (first line is shown bold)
        alt    optional secondary value (dashed line)
        lo/hi  optional range around y (shaded band, e.g. a credible interval)
        strip  optional colour for a tick in the bottom result strip
    """

    viewChanged = Signal(int, int, bool)  # first, last index, is_custom

    def __init__(self, accent="#4A9FD8", parent=None):
        super().__init__(parent)
        self.accent = QColor(accent)
        self.alt_color = QColor(255, 255, 255, 110)
        self.points = []
        self.auto_view = (0, -1)
        self.view = (0, -1)
        self.custom = False
        self.y_format = lambda v: f"{v:g}"
        self.y_clamp = None
        self.y_include = ()
        self.y_min_pad = 1.0
        self.ref_lines = []  # (value, label, QColor)
        self.empty_text = "No data yet"
        self._hover = -1
        self._drag_from = None
        self._drag_to = None
        self._reveal = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._set_reveal)
        self._signature = None
        self.setMouseTracking(True)
        self.setMinimumSize(280, 190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFont(chart_font())

    # ── data ─────────────────────────────────────────────────────────
    def set_data(self, points, auto_view=None, animate=True):
        self.points = list(points or [])
        n = len(self.points)
        if auto_view is None:
            auto_view = (0, n - 1)
        first, last = auto_view
        first = max(0, min(first, n - 1))
        last = max(first, min(last, n - 1))
        self.auto_view = (first, last)
        signature = (n, self.auto_view, tuple(p.get("y") for p in self.points[-5:]))
        changed = signature != self._signature
        self._signature = signature
        if changed or not self.custom or self.view[1] >= n:
            self.view = self.auto_view
            self.custom = False
        self._hover = -1
        if changed and animate and n:
            self._anim.stop()
            self._anim.start()
        self.update()
        self.viewChanged.emit(self.view[0], self.view[1], self.custom)

    def reset_view(self):
        self.view = self.auto_view
        self.custom = False
        self._hover = -1
        self.update()
        self.viewChanged.emit(self.view[0], self.view[1], self.custom)

    def visible_points(self):
        first, last = self.view
        return self.points[first:last + 1] if self.points and last >= first else []

    def _set_reveal(self, value):
        self._reveal = float(value)
        self.update()

    # ── geometry ─────────────────────────────────────────────────────
    def _y_axis(self, plot_height):
        visible = self.visible_points()
        values = [p["y"] for p in visible] + [p.get(k) for p in visible for k in ("alt", "lo", "hi")]
        max_ticks = max(2, int(plot_height // 34))
        return auto_y_range(values, max_ticks, self.y_min_pad, self.y_include, self.y_clamp)

    def _layout(self):
        fm = QFontMetrics(self.font())
        top = 10
        bottom = fm.height() + 10
        plot_h = max(40, self.height() - top - bottom)
        lo, hi, step = self._y_axis(plot_h)
        ticks = []
        value = lo
        while value <= hi + step * 1e-6:
            ticks.append(value)
            value += step
        label_w = max((fm.horizontalAdvance(self.y_format(v)) for v in ticks), default=20)
        left = label_w + 12
        plot = QRectF(left, top, max(40, self.width() - left - 12), plot_h)
        return plot, lo, hi, ticks

    def _x(self, plot, index):
        first, last = self.view
        if last <= first:
            return plot.center().x()
        return plot.left() + (index - first) / (last - first) * plot.width()

    def _y(self, plot, lo, hi, value):
        return plot.bottom() - (value - lo) / (hi - lo) * plot.height()

    def _index_at(self, plot, x):
        first, last = self.view
        if last < first:
            return -1
        if last == first:
            return first
        frac = (x - plot.left()) / plot.width()
        return int(round(first + frac * (last - first)))

    # ── painting ─────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setFont(self.font())
        fm = QFontMetrics(self.font())
        visible = self.visible_points()
        if not visible:
            p.setPen(TEXT)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty_text)
            p.end()
            return

        plot, lo, hi, ticks = self._layout()
        first, last = self.view

        # y grid + labels
        for value in ticks:
            y = self._y(plot, lo, hi, value)
            p.setPen(QPen(GRID, 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(TEXT)
            label = self.y_format(value)
            p.drawText(QRectF(0, y - fm.height() / 2, plot.left() - 8, fm.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)

        # reference lines (50 %, league thresholds); labels that would
        # collide with the one above are dropped, the line stays
        last_label_y = None
        for value, label, color in sorted(self.ref_lines, key=lambda r: -r[0]):
            if not (lo < value < hi):
                continue
            y = self._y(plot, lo, hi, value)
            pen = QPen(color, 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            if label and (last_label_y is None or y - last_label_y >= fm.height() + 2):
                last_label_y = y
                p.drawText(QRectF(plot.left(), y - fm.height() - 1, plot.width() - 4, fm.height()),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, label)

        self._paint_day_axis(p, plot, fm)

        # clip to the reveal animation
        p.save()
        p.setClipRect(QRectF(plot.left() - 6, 0, (plot.width() + 12) * self._reveal, self.height()))

        coords = [QPointF(self._x(plot, i), self._y(plot, lo, hi, self.points[i]["y"]))
                  for i in range(first, last + 1)]

        # shaded range (lo..hi) - replaces the area fill when present
        band = [(i, self.points[i].get("lo"), self.points[i].get("hi")) for i in range(first, last + 1)]
        band = [(self._x(plot, i), self._y(plot, lo, hi, a), self._y(plot, lo, hi, b))
                for i, a, b in band if a is not None and b is not None]
        if len(band) > 1:
            upper = [QPointF(x, yb) for x, _ya, yb in band]
            lower = [QPointF(x, ya) for x, ya, _yb in reversed(band)]
            shape = QPainterPath(upper[0])
            for pt in upper[1:] + lower:
                shape.lineTo(pt)
            shape.closeSubpath()
            fill = QColor(self.accent)
            fill.setAlpha(46)
            p.fillPath(shape, fill)
            edge = QColor(self.accent)
            edge.setAlpha(90)
            p.setPen(QPen(edge, 0.8))
            for edge_pts in (upper, lower):
                path = QPainterPath(edge_pts[0])
                for pt in edge_pts[1:]:
                    path.lineTo(pt)
                p.drawPath(path)

        # area under the line
        if len(coords) > 1 and len(band) < 2:
            area = QPainterPath(QPointF(coords[0].x(), plot.bottom()))
            for pt in coords:
                area.lineTo(pt)
            area.lineTo(QPointF(coords[-1].x(), plot.bottom()))
            area.closeSubpath()
            grad = QLinearGradient(0, plot.top(), 0, plot.bottom())
            top_c = QColor(self.accent)
            top_c.setAlpha(70)
            bottom_c = QColor(self.accent)
            bottom_c.setAlpha(0)
            grad.setColorAt(0, top_c)
            grad.setColorAt(1, bottom_c)
            p.fillPath(area, grad)

        # secondary (dashed) series
        alt = [(i, self.points[i].get("alt")) for i in range(first, last + 1)]
        alt = [QPointF(self._x(plot, i), self._y(plot, lo, hi, v)) for i, v in alt if v is not None]
        if len(alt) > 1:
            p.setPen(QPen(self.alt_color, 1.3, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(alt[0])
            for pt in alt[1:]:
                path.lineTo(pt)
            p.drawPath(path)

        # main line
        if len(coords) > 1:
            pen = QPen(self.accent, 2.2)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(coords[0])
            for pt in coords[1:]:
                path.lineTo(pt)
            p.drawPath(path)

        # markers (only while they don't crowd the line)
        spacing = plot.width() / max(1, last - first)
        if spacing >= 7 or len(coords) == 1:
            radius = 3.2 if spacing >= 14 else 2.4
            for offset, pt in enumerate(coords):
                color = self.points[first + offset].get("dot") or self.accent
                p.setPen(QPen(QColor(10, 14, 20, 220), 1.2))
                p.setBrush(QColor(color))
                p.drawEllipse(pt, radius, radius)

        # result strip along the bottom edge
        strip_h = 4
        for i in range(first, last + 1):
            color = self.points[i].get("strip")
            if color is None:
                continue
            x = self._x(plot, i)
            w = max(2.0, min(10.0, spacing * 0.7))
            p.fillRect(QRectF(x - w / 2, plot.bottom() - strip_h, w, strip_h), QColor(color))
        p.restore()

        # drag selection
        if self._drag_from is not None and self._drag_to is not None:
            x0, x1 = sorted((self._drag_from, self._drag_to))
            sel = QColor(self.accent)
            sel.setAlpha(40)
            p.fillRect(QRectF(x0, plot.top(), x1 - x0, plot.height()), sel)

        # hover crosshair + tooltip
        if first <= self._hover <= last:
            pt = coords[self._hover - first]
            p.setPen(QPen(QColor(255, 255, 255, 60), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(pt.x(), plot.top()), QPointF(pt.x(), plot.bottom()))
            ring = QColor(self.points[self._hover].get("dot") or self.accent)
            p.setPen(QPen(QColor(255, 255, 255, 230), 1.6))
            p.setBrush(ring)
            p.drawEllipse(pt, 5, 5)
            self._paint_tooltip(p, plot, pt, self.points[self._hover].get("tip") or [])
        p.end()

    def _paint_day_axis(self, p, plot, fm):
        first, last = self.view
        pts = self.points
        same_day = pts[first]["t"].date() == pts[last]["t"].date() if pts[first].get("t") and pts[last].get("t") else False
        candidates = []
        for i in range(first, last + 1):
            t = pts[i].get("t")
            if t is None:
                continue
            if same_day:
                candidates.append((i, _fmt_time(t)))
            elif i == first or (pts[i - 1].get("t") and t.date() != pts[i - 1]["t"].date()):
                if i != first:
                    x = (self._x(plot, i - 1) + self._x(plot, i)) / 2
                    p.setPen(QPen(DAY_LINE, 1, Qt.PenStyle.DotLine))
                    p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
                label = _fmt_day(t)
                if t.year != datetime.now().year:
                    label += f" '{t:%y}"
                candidates.append((i, label))
        # Newest label wins: place from the right so the latest day is always shown.
        placed_left = self.width() + 1
        p.setPen(TEXT)
        y = plot.bottom() + 6
        for i, label in reversed(candidates):
            w = fm.horizontalAdvance(label)
            x = self._x(plot, i) - w / 2
            x = max(plot.left() - 4, min(x, self.width() - w - 2))
            if x + w + 10 > placed_left:
                continue
            p.drawText(QRectF(x, y, w + 1, fm.height()), Qt.AlignmentFlag.AlignLeft, label)
            placed_left = x

    def _paint_tooltip(self, p, plot, anchor, lines):
        if not lines:
            return
        bold = QFont(self.font())
        bold.setBold(True)
        bold.setPixelSize(self.font().pixelSize() + 2 if self.font().pixelSize() > 0 else 12)
        fm_b, fm = QFontMetrics(bold), QFontMetrics(self.font())
        widths = [fm_b.horizontalAdvance(lines[0])] + [fm.horizontalAdvance(s) for s in lines[1:]]
        w = max(widths) + 20
        h = fm_b.height() + fm.height() * (len(lines) - 1) + 14
        x = anchor.x() + 12
        if x + w > self.width() - 4:
            x = anchor.x() - w - 12
        x = max(4, x)
        y = max(plot.top(), min(anchor.y() - h / 2, plot.bottom() - h))
        box = QRectF(x, y, w, h)
        p.setPen(QPen(QColor(self.accent.red(), self.accent.green(), self.accent.blue(), 150), 1))
        p.setBrush(QColor(14, 18, 26, 238))
        p.drawRoundedRect(box, 7, 7)
        p.setFont(bold)
        p.setPen(TEXT_STRONG)
        p.drawText(QRectF(x + 10, y + 7, w - 20, fm_b.height()), Qt.AlignmentFlag.AlignLeft, lines[0])
        p.setFont(self.font())
        p.setPen(QColor(214, 225, 240, 200))
        line_y = y + 7 + fm_b.height()
        for line in lines[1:]:
            p.drawText(QRectF(x + 10, line_y, w - 20, fm.height()), Qt.AlignmentFlag.AlignLeft, line)
            line_y += fm.height()

    # ── interaction ──────────────────────────────────────────────────
    @staticmethod
    def _pos(event):
        return event.position() if hasattr(event, "position") else QPointF(event.pos())

    def mouseMoveEvent(self, event):
        if not self.points:
            return
        pos = self._pos(event)
        plot = self._layout()[0]
        if self._drag_from is not None:
            self._drag_to = max(plot.left(), min(pos.x(), plot.right()))
        index = self._index_at(plot, pos.x())
        first, last = self.view
        index = index if first <= index <= last else -1
        if index != self._hover or self._drag_from is not None:
            self._hover = index
            self.update()

    def leaveEvent(self, event):
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.reset_view()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.points:
            self._drag_from = self._pos(event).x()
            self._drag_to = None

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._drag_from is None:
            return
        start, end = self._drag_from, self._drag_to
        self._drag_from = self._drag_to = None
        if end is not None and abs(end - start) > 8:
            plot = self._layout()[0]
            a = self._index_at(plot, min(start, end))
            b = self._index_at(plot, max(start, end))
            first, last = self.view
            a, b = max(first, a), min(last, b)
            if b - a >= 1 and (a, b) != self.view:
                self.view = (a, b)
                self.custom = True
                self.viewChanged.emit(a, b, True)
        self.update()

    def mouseDoubleClickEvent(self, event):
        self.reset_view()

    def wheelEvent(self, event):
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                bar = parent.verticalScrollBar()
                if bar is not None and bar.maximum() > 0:
                    bar.setValue(bar.value() - event.angleDelta().y())
                    event.accept()
                    return
            parent = parent.parent()
        event.ignore()
