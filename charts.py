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


# ── Meta trend (several archetypes over time) ─────────────────────────────
# Categorical palette: the dataviz reference instance, dark-surface steps,
# validated against the dashboard surface (#0B0F17): adjacent CVD dE >= 8.4,
# normal-vision dE >= 19.3, contrast >= 3:1. Fixed order, never cycled into
# new hues: slots 9-16 reuse the hues with a dashed line / hatched fill.
SERIES_COLORS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
MAX_SERIES = 2 * len(SERIES_COLORS)
SURFACE = QColor(11, 15, 23)


def series_style(slot):
    """(QColor, dashed) for a colour slot 0..15."""
    return QColor(SERIES_COLORS[slot % len(SERIES_COLORS)]), slot >= len(SERIES_COLORS)


class TrendChart(QWidget):
    """Shares or counts of several archetypes per day (TrainerHill meta trend).

    set_data(dates, series, mode, stacked): dates are ISO strings; each series
    is {"id", "name", "slot", "values": [...]} (one value per date).
    mode "share" (percent) or "count"; stacked draws areas instead of lines.
    Hover: crosshair + a tooltip with every series on that day.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dates = []
        self.series = []
        self.mode = "share"
        self.stacked = False
        self.focus = None  # series id to highlight (legend hover)
        self.empty_text = "Pick decks to compare"
        self._hover = -1
        self._reveal = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._set_reveal)
        self.setMouseTracking(True)
        self.setMinimumSize(320, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFont(chart_font())

    def set_data(self, dates, series, mode="share", stacked=False, animate=True):
        self.dates = [datetime.strptime(d[:10], "%Y-%m-%d") for d in dates]
        self.series = list(series)
        self.mode = mode
        self.stacked = stacked
        self._hover = -1
        if animate and self.series:
            self._anim.stop()
            self._anim.start()
        else:
            self._reveal = 1.0
        self.update()

    def set_focus(self, series_id):
        if series_id != self.focus:
            self.focus = series_id
            self.update()

    def _set_reveal(self, value):
        self._reveal = float(value)
        self.update()

    # ── geometry ──
    def _labels_inline(self):
        return not self.stacked and 0 < len(self.series) <= 4

    def _plot(self):
        fm = QFontMetrics(self.font())
        right = 14
        if self._labels_inline():
            right += max(fm.horizontalAdvance(s["name"]) for s in self.series) + 14
        return QRectF(46, 12, max(10.0, self.width() - 46 - right), max(10.0, self.height() - 12 - 28))

    def _stacks(self):
        """Per series: (lower, upper) value lists (lines: lower = None)."""
        out = []
        base = [0.0] * len(self.dates)
        for s in self.series:
            vals = [float(v or 0) for v in s["values"]]
            if self.stacked:
                upper = [b + v for b, v in zip(base, vals)]
                out.append((list(base), upper))
                base = upper
            else:
                out.append((None, vals))
        return out

    def _y_range(self, stacks, plot):
        top = max([max(up) for _lo, up in stacks if up] or [1.0])
        if self.mode == "share" and self.stacked:
            top = 100.0
        step = nice_step(top, max(2, int(plot.height() // 42)))
        hi = max(step, math.ceil(top / step - 1e-9) * step)
        if self.mode == "share":
            hi = min(hi, 100.0)
        return 0.0, hi, step

    def _x(self, plot, i):
        n = len(self.dates)
        return plot.left() + (plot.width() * i / (n - 1) if n > 1 else plot.width() / 2)

    def _y(self, plot, lo, hi, v):
        return plot.bottom() - (v - lo) / (hi - lo) * plot.height() * self._reveal

    def _fmt(self, v):
        return f"{v:.1f}%" if self.mode == "share" else f"{v:,.0f}"

    # ── painting ──
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(self.font())
        fm = QFontMetrics(self.font())
        if not self.dates or not self.series:
            p.setPen(TEXT)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty_text)
            return
        plot = self._plot()
        stacks = self._stacks()
        lo, hi, step = self._y_range(stacks, plot)

        # recessive grid + y labels
        v = lo
        while v <= hi + 1e-9:
            y = plot.bottom() - (v - lo) / (hi - lo) * plot.height()  # grid doesn't animate
            p.setPen(QPen(GRID, 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(TEXT)
            label = f"{v:g}%" if self.mode == "share" else f"{v:,.0f}"
            p.drawText(QRectF(0, y - 8, plot.left() - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       label)
            v += step

        # x labels: evenly spaced dates, skipped when they would collide
        last_right = -1e9
        n = len(self.dates)
        stride = max(1, math.ceil(n / max(1, plot.width() / 64)))
        for i in range(n - 1, -1, -stride):  # newest first, so the latest day is always labelled
            text = _fmt_day(self.dates[i])
            w = fm.horizontalAdvance(text)
            x = min(max(self._x(plot, i) - w / 2, plot.left() - 10), plot.right() - w + 6)
            if last_right != -1e9 and x + w + 8 > last_right:
                continue
            p.setPen(TEXT)
            p.drawText(QRectF(x, plot.bottom() + 8, w + 2, 16), Qt.AlignmentFlag.AlignLeft, text)
            last_right = x

        dim = self.focus is not None
        order = range(len(self.series))
        if self.stacked:
            for k in order:
                s, (lower, upper) = self.series[k], stacks[k]
                color, hatched = series_style(s["slot"])
                fill = QColor(color)
                fill.setAlpha(70 if dim and s["id"] != self.focus else 215)
                path = QPainterPath(QPointF(self._x(plot, 0), self._y(plot, lo, hi, upper[0])))
                for i in range(1, n):
                    path.lineTo(self._x(plot, i), self._y(plot, lo, hi, upper[i]))
                for i in range(n - 1, -1, -1):
                    path.lineTo(self._x(plot, i), self._y(plot, lo, hi, lower[i]))
                path.closeSubpath()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(fill)
                p.drawPath(path)
                if hatched:  # slots 9-16: same hue + texture, never a new hue
                    p.setBrush(_hatch_brush(SURFACE))
                    p.drawPath(path)
                # 2px surface gap between layers
                edge = QPainterPath(QPointF(self._x(plot, 0), self._y(plot, lo, hi, upper[0])))
                for i in range(1, n):
                    edge.lineTo(self._x(plot, i), self._y(plot, lo, hi, upper[i]))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(SURFACE, 2))
                p.drawPath(edge)
        else:
            for k in order:
                s, upper = self.series[k], stacks[k][1]
                color, dashed = series_style(s["slot"])
                if dim and s["id"] != self.focus:
                    color.setAlpha(55)
                path = QPainterPath(QPointF(self._x(plot, 0), self._y(plot, lo, hi, upper[0])))
                for i in range(1, n):
                    path.lineTo(self._x(plot, i), self._y(plot, lo, hi, upper[i]))
                pen = QPen(color, 2.6 if s["id"] == self.focus else 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                if dashed:
                    pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
            if self._labels_inline():
                self._paint_end_labels(p, plot, stacks, lo, hi, fm)

        if 0 <= self._hover < n:
            x = self._x(plot, self._hover)
            p.setPen(QPen(QColor(255, 255, 255, 60), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            for k, s in enumerate(self.series):
                color, _ = series_style(s["slot"])
                y = self._y(plot, lo, hi, stacks[k][1][self._hover])
                p.setPen(QPen(SURFACE, 2))
                p.setBrush(color)
                p.drawEllipse(QPointF(x, y), 4, 4)
            self._paint_tooltip(p, plot, x)

    def _paint_end_labels(self, p, plot, stacks, lo, hi, fm):
        """Direct labels at the line ends (<= 4 series), nudged apart."""
        items = sorted(((self._y(plot, lo, hi, up[-1]), s) for s, (_l, up) in zip(self.series, stacks)),
                       key=lambda t: t[0])
        placed = []
        for y, s in items:
            y = max(y, placed[-1] + fm.height()) if placed else y
            placed.append(y)
            color, _ = series_style(s["slot"])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(plot.right() + 10, y), 3, 3)
            p.setPen(TEXT_STRONG)
            p.drawText(QRectF(plot.right() + 18, y - fm.height() / 2, self.width() - plot.right() - 18, fm.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, s["name"])

    def _paint_tooltip(self, p, plot, x):
        i = self._hover
        rows = sorted(((float(s["values"][i] or 0), s) for s in self.series), key=lambda t: -t[0])
        shown = rows[:12]
        bold = QFont(self.font())
        bold.setBold(True)
        fm, fm_b = QFontMetrics(self.font()), QFontMetrics(bold)
        title = f"{self.dates[i]:%a} {_fmt_day(self.dates[i])}"
        lines = [(s, f"{s['name']}", self._fmt(v)) for v, s in shown]
        name_w = max([fm.horizontalAdvance(n) for _s, n, _v in lines] + [fm_b.horizontalAdvance(title)])
        val_w = max(fm.horizontalAdvance(v) for _s, _n, v in lines)
        w = 14 + name_w + 16 + val_w + 12
        extra = len(rows) - len(shown)
        h = fm_b.height() + fm.height() * (len(lines) + (1 if extra else 0)) + 16
        bx = x + 14 if x + 14 + w < self.width() - 4 else x - w - 14
        by = plot.top() + 4
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(14, 18, 26, 240))
        p.drawRoundedRect(QRectF(bx, by, w, h), 7, 7)
        p.setFont(bold)
        p.setPen(TEXT_STRONG)
        p.drawText(QRectF(bx + 10, by + 7, w - 20, fm_b.height()), Qt.AlignmentFlag.AlignLeft, title)
        p.setFont(self.font())
        ly = by + 8 + fm_b.height()
        for s, name, value in lines:
            color, _ = series_style(s["slot"])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(bx + 10, ly + fm.height() / 2 - 3, 6, 6), 1.5, 1.5)
            p.setPen(QColor(214, 225, 240, 215))
            p.drawText(QRectF(bx + 22, ly, name_w, fm.height()), Qt.AlignmentFlag.AlignLeft, name)
            p.setPen(TEXT_STRONG)
            p.drawText(QRectF(bx + 10, ly, w - 20, fm.height()), Qt.AlignmentFlag.AlignRight, value)
            ly += fm.height()
        if extra:
            p.setPen(TEXT)
            p.drawText(QRectF(bx + 22, ly, w - 30, fm.height()), Qt.AlignmentFlag.AlignLeft, f"+{extra} more")

    # ── interaction ──
    def mouseMoveEvent(self, event):
        if not self.dates:
            return
        plot = self._plot()
        x = event.position().x()
        n = len(self.dates)
        i = 0 if n == 1 else round((x - plot.left()) / plot.width() * (n - 1))
        i = max(0, min(n - 1, i))
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, _event):
        self._hover = -1
        self.update()

    def wheelEvent(self, event):
        event.ignore()


def _hatch_brush(color):
    """Diagonal hatch (45 degrees) in the surface colour, for texture slots."""
    from PySide6.QtGui import QBrush
    return QBrush(color, Qt.BrushStyle.BDiagPattern)


# ── Rank per deck (deck page) ─────────────────────────────────────────────
WIN_COLOR, LOSS_COLOR, TIE_COLOR = "#66BB6A", "#EF5350", "#9AA5B1"
RANK_ACCENT = "#F9A825"  # same as the dashboard RANK chart


def _result_kind(result):
    value = (result or "").strip().lower()
    if value.startswith("w"):
        return "W"
    if value.startswith("l"):
        return "L"
    return "T"


def deck_rank_points(battles):
    """SeriesChart points for one deck's ladder rank: one per game with a
    recorded `my_rank` (oldest first), marker and strip coloured by result.
    `battles` are BattleDatabase.get_deck_battles_detailed() dicts."""
    from leagues import league_name
    points = []
    prev = None
    for b in battles:
        rank = b.get("my_rank")
        if rank is None:
            continue
        try:
            rank = int(rank)
            when = datetime.fromisoformat(str(b.get("timestamp")))
        except (TypeError, ValueError):
            continue
        kind = _result_kind(b.get("result"))
        color = {"W": WIN_COLOR, "L": LOSS_COLOR, "T": TIE_COLOR}[kind]
        label = {"W": "Win", "L": "Loss", "T": "Tie"}[kind]
        day = _fmt_day(when) + (f", {when.year}" if when.year != datetime.now().year else "")
        tip = [f"{rank:,}   {league_name(rank)}",
               f"Game {len(points) + 1} · {day} · {_fmt_time(when)}",
               f"{label} vs {b['opponent']}" if b.get("opponent") else label]
        if prev is not None and rank != prev:
            tip.append(f"{rank - prev:+,} since this deck's previous game")
        points.append({"y": rank, "t": when, "dot": color, "strip": color, "tip": tip, "result": kind})
        prev = rank
    return points


def deck_rank_summary(points):
    """One line under the chart: first → last rank, change, peak, record."""
    if not points:
        return ""
    first, last = points[0]["y"], points[-1]["y"]
    peak = max(p["y"] for p in points)
    wins = sum(1 for p in points if p.get("result") == "W")
    losses = sum(1 for p in points if p.get("result") == "L")
    ties = len(points) - wins - losses
    record = f"{wins}-{losses}" + (f"-{ties}" if ties else "")
    return (f"{first:,} → {last:,} ({last - first:+,}) over {len(points)} ranked games ({record})"
            f" · peak {peak:,}")


def make_deck_rank_chart(points, height=180):
    """A compact SeriesChart for deck_rank_points(), styled like the
    dashboard RANK chart (league thresholds as reference lines)."""
    from leagues import LEAGUES
    chart = SeriesChart(RANK_ACCENT)
    chart.y_format = lambda v: f"{v:,.0f}"
    chart.y_min_pad = 6
    chart.y_clamp = (0, float("inf"))
    chart.empty_text = "No ranked games with this deck"
    chart.ref_lines = [(threshold, name, QColor(249, 168, 37, 70)) for threshold, _key, name in LEAGUES if threshold > 0]
    chart.setMinimumSize(240, height)
    chart.setMaximumHeight(height)
    chart.set_data(points, animate=False)
    return chart
