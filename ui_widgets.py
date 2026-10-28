"""
Small custom-painted widgets for the dashboard.

DeckFlagButton - pin / star / ignore toggles on a deck page. Icons are drawn
with QPainter (no emoji / font glyphs). Pressing squeezes the icon, releasing
springs it back with a slight overshoot; switching ON adds a soft ring (and a
few sparks for the star).

DeckTabBar - deck tab bar that marks pinned tabs with a small dot and dims
ignored ones, independent of the tab stylesheet.

DeckTitle - a deck page's name, renamed in place: double-click it to edit;
Enter saves, Esc cancels. Typing
another deck's name offers to merge into it, and only then.
"""

import math

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QVariantAnimation, QEasingCurve, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QLineEdit, QStyledItemDelegate, QTabBar,
                               QVBoxLayout, QWidget)


FLAG_STYLES = {
    # kind: (accent, tooltip when off, tooltip when on)
    "pin": ("#4A9FD8", "Pin to front", "Unpin"),
    "star": ("#F9A825", "Add to Meta tab", "Remove from Meta tab"),
    "ignore": ("#EF5350", "Hide from stats", "Show in stats"),
}


def _anim(owner, setter, duration, curve):
    anim = QVariantAnimation(owner)
    anim.setDuration(duration)
    anim.setEasingCurve(curve)
    anim.valueChanged.connect(setter)
    return anim


class DeckTitle(QWidget):
    """A deck page's name that renames in place (no dialog).

    rename_requested(new_name, merge): emitted on Enter. merge is True when
    the typed name is another deck's (case-insensitive; new_name is then that
    deck's exact name), shown first as a line under the name. Esc, or leaving
    the field while it would merge, cancels; leaving it on a plain new name saves.
    """

    rename_requested = Signal(str, bool)

    STYLE = """
        QLineEdit#deckTitleEdit { background: transparent; border: none; border-bottom: 1px solid transparent;
                                  color: rgba(246,250,255,0.98); font-size: 24px; font-weight: 700; padding: 0; }
        QLineEdit#deckTitleEdit[editing="true"] { border-bottom: 1px solid rgba(74,159,216,0.70); }
        QLabel#deckTitleHint { color: rgba(232,194,106,0.95); font-size: 10px; }
    """

    def __init__(self, name, other_names=(), parent=None):
        super().__init__(parent)
        self.name = name
        self._others = {n.casefold(): n for n in other_names if n and n != name}
        self.setStyleSheet(self.STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.edit = QLineEdit(name)
        self.edit.setObjectName("deckTitleEdit")
        self.edit.setReadOnly(True)
        self.edit.setFrame(False)
        self.edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.edit.setCursor(Qt.CursorShape.ArrowCursor)
        self.edit.setToolTip("Double-click to rename")
        self.edit.installEventFilter(self)
        self.edit.textEdited.connect(self._on_text)
        self.edit.returnPressed.connect(self._commit)
        row.addWidget(self.edit)
        row.addStretch()
        outer.addLayout(row)
        self.hint = QLabel("")
        self.hint.setObjectName("deckTitleHint")
        self.hint.setVisible(False)
        outer.addWidget(self.hint)
        self._merge_into = None
        self._fit()

    def _fit(self):
        """Read-only: exactly as wide as the name. Editing: room to type.
        Measured with the stylesheet's font, so it's polished first."""
        self.edit.ensurePolished()
        width = QFontMetrics(self.edit.font()).horizontalAdvance(self.edit.text() or " ") + 6
        if not self.edit.isReadOnly():
            width = max(width + 24, 260)
        self.edit.setMinimumWidth(width)
        self.edit.setMaximumWidth(width)

    def showEvent(self, event):
        self._fit()  # the page's own stylesheet (Text size) applies by now
        super().showEvent(event)

    def _set_editing(self, on):
        self.edit.setReadOnly(not on)
        self.edit.setProperty("editing", on)
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)
        self.edit.setCursor(Qt.CursorShape.IBeamCursor if on else Qt.CursorShape.ArrowCursor)
        self._fit()

    def start_editing(self):
        self._set_editing(True)
        self.edit.setFocus()
        self.edit.selectAll()

    def cancel(self):
        self.edit.setText(self.name)
        self._merge_into = None
        self.hint.setVisible(False)
        self._set_editing(False)

    def _on_text(self, text):
        self._merge_into = self._others.get(text.strip().casefold())
        if self._merge_into:
            self.hint.setText(f"You already have a \u201c{self._merge_into}\u201d deck. "
                              f"Enter merges this deck's battles into it \u00b7 Esc cancels")
        self.hint.setVisible(bool(self._merge_into))
        self._fit()

    def _commit(self):
        new = self.edit.text().strip()
        merge = self._merge_into
        if not new or new == self.name:
            self.cancel()
            return
        self.hint.setVisible(False)
        self._set_editing(False)
        self.rename_requested.emit(merge or new, bool(merge))

    def eventFilter(self, obj, event):
        if obj is self.edit:
            kind = event.type()
            if kind == event.Type.MouseButtonDblClick and self.edit.isReadOnly():
                self.start_editing()
                return True
            if kind == event.Type.KeyPress and event.key() == Qt.Key.Key_Escape and not self.edit.isReadOnly():
                self.cancel()
                return True
            if kind == event.Type.FocusOut and not self.edit.isReadOnly():
                # Leaving the field saves a plain rename; a merge needs Enter.
                if self._merge_into or not self.edit.text().strip():
                    self.cancel()
                else:
                    self._commit()
        return super().eventFilter(obj, event)


def _star_path(cx, cy, outer, inner):
    poly = QPolygonF()
    for i in range(10):
        r = outer if i % 2 == 0 else inner
        a = -math.pi / 2 + i * math.pi / 5
        poly.append(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
    path = QPainterPath()
    path.addPolygon(poly)
    path.closeSubpath()
    return path


def _pin_path():
    """Push-pin in a 16x16 box, tilted like a pin stuck in a board."""
    path = QPainterPath()
    path.addRoundedRect(QRectF(5.0, 1.0, 6.0, 2.6), 1.0, 1.0)          # head
    body = QPolygonF([QPointF(6.2, 3.6), QPointF(9.8, 3.6), QPointF(11.2, 8.6), QPointF(4.8, 8.6)])
    path.addPolygon(body)
    path.closeSubpath()
    path.addRoundedRect(QRectF(3.0, 8.6, 10.0, 1.8), 0.9, 0.9)         # collar
    transform = QTransform()
    transform.translate(8, 8)
    transform.rotate(35)
    transform.translate(-8, -8)
    return transform.map(path)


def _eye_path():
    path = QPainterPath(QPointF(1.0, 8.0))
    path.quadTo(QPointF(8.0, 1.0), QPointF(15.0, 8.0))
    path.quadTo(QPointF(8.0, 15.0), QPointF(1.0, 8.0))
    path.closeSubpath()
    return path


class DeckFlagButton(QAbstractButton):
    """Checkable icon button: kind is 'pin', 'star' or 'ignore'."""

    SIZE = 34

    def __init__(self, kind, checked=False, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.accent = QColor(FLAG_STYLES[kind][0])
        self.setCheckable(True)
        self.setChecked(bool(checked))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._scale = 1.0
        self._on = 1.0 if checked else 0.0
        self._hover = 0.0
        self._burst = 1.0  # 1 = finished
        self._scale_anim = _anim(self, self._set_scale, 90, QEasingCurve.Type.OutQuad)
        self._on_anim = _anim(self, self._set_on, 200, QEasingCurve.Type.OutCubic)
        self._hover_anim = _anim(self, self._set_hover, 140, QEasingCurve.Type.OutCubic)
        self._burst_anim = _anim(self, self._set_burst, 460, QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._on_toggled)
        self._update_tooltip()

    def sizeHint(self):
        return QSize(self.SIZE, self.SIZE)

    # animation setters
    def _set_scale(self, v):
        self._scale = float(v)
        self.update()

    def _set_on(self, v):
        self._on = float(v)
        self.update()

    def _set_hover(self, v):
        self._hover = float(v)
        self.update()

    def _set_burst(self, v):
        self._burst = float(v)
        self.update()

    def _run(self, anim, start, end, duration=None, curve=None):
        anim.stop()
        if duration is not None:
            anim.setDuration(duration)
        if curve is not None:
            anim.setEasingCurve(curve)
        anim.setStartValue(float(start))
        anim.setEndValue(float(end))
        anim.start()

    def _update_tooltip(self):
        _accent, off_tip, on_tip = FLAG_STYLES[self.kind]
        self.setToolTip(on_tip if self.isChecked() else off_tip)

    def _on_toggled(self, checked):
        self._update_tooltip()
        self._run(self._on_anim, self._on, 1.0 if checked else 0.0)
        if checked:
            self._run(self._burst_anim, 0.0, 1.0)

    # events
    def enterEvent(self, event):
        self._run(self._hover_anim, self._hover, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._run(self._hover_anim, self._hover, 0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._run(self._scale_anim, self._scale, 0.82, 90, QEasingCurve.Type.OutQuad)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            curve = QEasingCurve(QEasingCurve.Type.OutBack)
            curve.setOvershoot(2.6)
            self._run(self._scale_anim, self._scale, 1.0, 340, curve)
        super().mouseReleaseEvent(event)

    def setChecked(self, checked):
        # Programmatic changes jump straight to the end state (no burst).
        super().setChecked(checked)
        if hasattr(self, "_on_anim"):
            self._on_anim.stop()
            self._burst_anim.stop()
            self._on = 1.0 if checked else 0.0
            self._burst = 1.0
            self.update()

    def nextCheckState(self):
        # Clicks animate (QAbstractButton calls this instead of setChecked).
        QAbstractButton.setChecked(self, not self.isChecked())

    # painting
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(3.5, 3.5, -3.5, -3.5)
        center = rect.center()
        on, hover = self._on, self._hover

        # background: neutral glass → accent tint
        bg = QColor(self.accent)
        bg.setAlpha(int(10 + 8 * hover + (46 - 10) * on))
        neutral = QColor(255, 255, 255, int(10 + 10 * hover))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(neutral if on < 0.02 else bg)
        border = QColor(self.accent)
        border.setAlpha(int(40 * hover + 150 * on))
        base_border = QColor(255, 255, 255, int(30 + 20 * hover))
        p.setPen(QPen(border if (on > 0.02 or hover > 0.02) else base_border, 1.0))
        p.drawRoundedRect(rect, 7, 7)

        # ring + sparks when switched on
        if self._burst < 1.0 and on > 0:
            t = self._burst
            ring = QColor(self.accent)
            ring.setAlpha(int(170 * (1.0 - t)))
            p.setPen(QPen(ring, 1.6 * (1.0 - t) + 0.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            r = 7 + 9 * t
            p.drawEllipse(center, r, r)
            if self.kind == "star":
                spark = QColor(self.accent)
                spark.setAlpha(int(220 * (1.0 - t)))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(spark)
                for i in range(6):
                    a = -math.pi / 2 + i * math.pi / 3 + math.pi / 6
                    d = 8 + 7 * t
                    p.drawEllipse(QPointF(center.x() + d * math.cos(a), center.y() + d * math.sin(a)),
                                  1.3 * (1.0 - t) + 0.3, 1.3 * (1.0 - t) + 0.3)

        # icon (16x16 design box, scaled by the press spring)
        p.save()
        p.translate(center)
        p.scale(self._scale, self._scale)
        p.translate(-8, -8)
        off_color = QColor(255, 255, 255, int(150 + 70 * hover))
        stroke = QColor(
            int(off_color.red() + (self.accent.red() - off_color.red()) * on),
            int(off_color.green() + (self.accent.green() - off_color.green()) * on),
            int(off_color.blue() + (self.accent.blue() - off_color.blue()) * on),
        )
        fill = QColor(self.accent)
        fill.setAlpha(int(255 * on))
        pen = QPen(stroke, 1.3)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(fill)
        if self.kind == "star":
            p.drawPath(_star_path(8, 8.4, 7.2, 3.0))
        elif self.kind == "pin":
            p.drawPath(_pin_path())
            # needle
            p.setBrush(Qt.BrushStyle.NoBrush)
            transform = QTransform()
            transform.translate(8, 8)
            transform.rotate(35)
            transform.translate(-8, -8)
            p.drawLine(transform.map(QPointF(8, 10.4)), transform.map(QPointF(8, 15.0)))
        else:
            eye = _eye_path()
            fill.setAlpha(int(70 * on))
            p.setBrush(fill)
            p.drawPath(eye)
            p.setBrush(stroke)
            p.drawEllipse(QPointF(8, 8), 2.1, 2.1)
            # the slash fades in when ignored; a gap keeps it readable on the eye
            slash = QColor(stroke)
            slash.setAlpha(int(255 * max(on, 0.0)))
            gap = QPen(QColor(20, 24, 32, int(230 * on)), 3.2)
            gap.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(gap)
            p.drawLine(QPointF(2.5, 13.5), QPointF(13.5, 2.5))
            line = QPen(slash, 1.5)
            line.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(line)
            p.drawLine(QPointF(2.5, 13.5), QPointF(13.5, 2.5))
        p.restore()
        p.end()


class DeckTabBar(QTabBar):
    """Marks pinned tabs (small accent dot) and dims ignored ones.
    Tabs are identified by their tooltip (the full deck name)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pinned = set()
        self.ignored = set()

    def set_flags(self, pinned, ignored):
        self.pinned = set(pinned or ())
        self.ignored = set(ignored or ())
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not (self.pinned or self.ignored):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for i in range(self.count()):
            name = self.tabToolTip(i)
            rect = QRectF(self.tabRect(i))
            if name in self.ignored:
                p.fillRect(rect.adjusted(1, 1, -1, -1), QColor(12, 14, 20, 120))
            if name in self.pinned:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(FLAG_STYLES["pin"][0]))
                p.drawEllipse(QPointF(rect.right() - 6, rect.top() + 6), 2.4, 2.4)
        p.end()


MINE_ROLE = Qt.ItemDataRole.UserRole + 7  # set on a row's column-0 item for "your deck" rows
MINE_ACCENT = QColor("#B39DDB")


class MineRowDelegate(QStyledItemDelegate):
    """Tints rows marked as your own deck and draws an accent bar at the
    row's left edge (the table stylesheet makes item backgrounds
    transparent, so per-item colours wouldn't show)."""

    def paint(self, painter, option, index):
        if index.sibling(index.row(), 0).data(MINE_ROLE):
            tint = QColor(MINE_ACCENT)
            tint.setAlpha(52)
            painter.fillRect(option.rect, tint)
            if index.column() == 0:
                painter.fillRect(QRectF(option.rect.left(), option.rect.top(), 4, option.rect.height()), MINE_ACCENT)
        super().paint(painter, option, index)


class EditHintDelegate(QStyledItemDelegate):
    """Shows a faint pencil in an editable cell while it's hovered, so
    "click to edit" needs no sentence."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        from PySide6.QtWidgets import QStyle
        if not (option.state & QStyle.StateFlag.State_MouseOver) or not (index.flags() & Qt.ItemFlag.ItemIsEditable):
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colour = QColor(214, 225, 240, 140)
        painter.setPen(QPen(colour, 1.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        r = option.rect
        x, y = r.right() - 14, r.center().y() + 4
        painter.drawLine(QPointF(x, y), QPointF(x + 7, y - 7))      # shaft
        painter.drawLine(QPointF(x, y), QPointF(x + 2.5, y - 0.6))  # tip
        painter.drawLine(QPointF(x, y), QPointF(x + 0.6, y - 2.5))
        painter.restore()
