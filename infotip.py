"""
Two-stage hover tips, replacing QToolTip app-wide.

A tip's text may hold MORE ("<!--more-->"): the part before it (the summary)
shows on hover; a small ⋯ in the corner says there is more. Right-click (or
Shift) slides the details open; a second right-click pins the tip so the
pointer can move away while reading - any click or Esc closes it. Tips
without MORE whose text runs long are split at the first line break, so no
tip opens as a wall of text.

install(app) hooks QEvent.ToolTip for every widget, item view cell and header
section, so existing setToolTip / ToolTipRole text keeps working. Widgets that
call QToolTip.showText themselves use show_text() / hide_text().

HintLabel - a faint how-to hint that shows only the first few times (or when
the user seems stuck) and fades out once the feature is used.
"""

import json
import os
import re
import time

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QRect, QTimer, QVariantAnimation, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QPainter, QTextDocument
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QHeaderView, QLabel, QVBoxLayout, QWidget)

MORE = "<!--more-->"
WHOLE = "<!--whole-->"  # never split: the whole tip shows on hover
MAX_WIDTH = 320
TICK_MS = 40
EXPAND_MS = 180
FADE_MS = 120
AUTO_SPLIT_WORDS = 14  # longer tips without MORE split at their first <br>

_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>", re.I)


def tip(summary, details=None):
    """Tip text: `summary` on hover, `details` on right-click."""
    return f"{summary}{MORE}{details}" if details else summary


def whole(text):
    """Tip text that always shows in full on hover (no right-click step)."""
    return WHOLE + text


def _words(html):
    return len(_TAG.sub(" ", html or "").split())


def split(text):
    """(summary, details or '') for a tip's text."""
    text = (text or "").strip()
    if text.startswith(WHOLE):
        return text[len(WHOLE):].strip(), ""
    if MORE in text:
        head, _, tail = text.partition(MORE)
        return head.strip(), tail.strip()
    if "<" not in text and "\n" in text:  # plain text: treat newlines as breaks
        text = text.replace("\n", "<br>")
    parts = _BR.split(text, maxsplit=1)
    if len(parts) == 2 and _words(text) > AUTO_SPLIT_WORDS and _words(parts[1]) > 3:
        return parts[0].strip(), parts[1].strip()
    return text, ""


def _colour(r, g, b, a=255):
    try:
        import theme
        return theme.qcolor(r, g, b, a)
    except Exception:
        from PySide6.QtGui import QColor
        return QColor(r, g, b, a)


class _Divider(QWidget):
    """1 px line between summary and details; accent while pinned."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.pinned = False

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), _colour(74, 159, 216, 150) if self.pinned else _colour(255, 255, 255, 26))
        p.end()


class InfoTip(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.frame = QFrame()
        self.frame.setObjectName("infoTip")
        self.frame.setStyleSheet("""
            QFrame#infoTip { background-color: rgb(16, 22, 32); border: 1px solid rgba(74, 159, 216, 0.55);
                             border-radius: 6px; }
            QLabel { background: transparent; border: none; color: rgba(232, 238, 246, 0.96); font-size: 11px; }
            QLabel#infoTipMore { color: rgba(200, 212, 228, 0.86); }
            QLabel#infoTipCue { color: rgba(200, 212, 228, 0.45); font-size: 12px; font-weight: 700; }
        """)
        outer.addWidget(self.frame)
        box = QVBoxLayout(self.frame)
        box.setContentsMargins(9, 6, 9, 7)
        box.setSpacing(5)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.cue = QLabel("⋯")  # there is more: right-click
        self.cue.setObjectName("infoTipCue")
        top.addWidget(self.summary)
        top.addWidget(self.cue, 0, Qt.AlignmentFlag.AlignBottom)
        box.addLayout(top)
        self.line = _Divider()
        self.details = QLabel()
        self.details.setObjectName("infoTipMore")
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        box.addWidget(self.line)
        box.addWidget(self.details)

        self.anchor = None
        self.anchor_rect = QRect()  # global
        self.text = ""
        self.has_more = False
        self.expanded = False
        self.pinned = False
        self._tick = QTimer(self)
        self._tick.setInterval(TICK_MS)
        self._tick.timeout.connect(self._on_tick)
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(self._on_fade)
        self._grow = QVariantAnimation(self)
        self._grow.setDuration(EXPAND_MS)
        self._grow.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._grow.valueChanged.connect(self._on_grow)
        self._target = QPoint()

    # ── content ───────────────────────────────────────────────────────────
    def _width_for(self, *parts):
        doc = QTextDocument()
        doc.setDefaultFont(self.summary.font())
        ideal = 0
        for part in parts:
            if part:
                doc.setHtml(part)
                ideal = max(ideal, doc.idealWidth())
        return int(min(MAX_WIDTH, ideal + 4))

    def show_tip(self, global_pos, text, anchor, rect):
        """Show `text` near `global_pos` while the pointer stays in `rect`
        (global) over `anchor`."""
        if self.pinned:
            return  # a pinned tip stays until a click or Esc
        if not text:
            self.hide_tip()
            return
        switching = self.isVisible() and self.windowOpacity() > 0.5
        if self.isVisible() and text == self.text:
            self.anchor, self.anchor_rect = anchor, rect
            return
        summary, details = split(text)
        self.text = text
        self.anchor, self.anchor_rect = anchor, rect
        self.has_more = bool(details)
        self.expanded = False
        width = self._width_for(summary, details)
        self.summary.setText(summary)
        self.summary.setFixedWidth(width)
        self.details.setText(details)
        self.details.setFixedWidth(width + (self.cue.sizeHint().width() + 6 if self.has_more else 0))
        self.details.setMaximumHeight(0)
        self.details.setVisible(self.has_more)
        self.cue.setVisible(self.has_more)
        self.line.hide()
        self.line.pinned = False
        self._grow.stop()
        self._fit()
        self._target = self._place(global_pos)
        if switching:  # moving between cells: no fade, just swap
            self._fade.stop()
            self.setWindowOpacity(1.0)
            self.move(self._target)
        else:
            self.setWindowOpacity(0.0)
            self.move(self._target + QPoint(0, 4))
            self.show()
            self._fade.stop()
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        self.raise_()
        self._tick.start()

    def hide_tip(self):
        self._tick.stop()
        self._fade.stop()
        self._grow.stop()
        self.anchor = None
        self.text = ""
        self.expanded = self.pinned = False
        self.hide()

    def advance(self):
        """Right-click: summary -> details -> pinned -> closed. False when the
        tip has nothing more to show (the click is then left to the widget)."""
        if not self.isVisible() or not self.has_more:
            return False
        if not self.expanded:
            self.expand()
        elif not self.pinned:
            self.pinned = True
            self.line.pinned = True
            self.line.update()
        else:
            self.hide_tip()
        return True

    def expand(self):
        if not self.has_more or self.expanded:
            return
        self.expanded = True
        self.cue.hide()
        self.line.show()
        full = self.details.heightForWidth(self.details.width())
        self._grow.stop()
        self._grow.setStartValue(0)
        self._grow.setEndValue(max(1, full))
        self._grow.start()

    # ── geometry ──────────────────────────────────────────────────────────
    def _screen_rect(self, pos):
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

    def _place(self, cursor):
        area = self._screen_rect(cursor)
        size = self.size()
        x = cursor.x() + 14
        y = cursor.y() + 20
        if x + size.width() > area.right():
            x = max(area.left(), cursor.x() - size.width() - 8)
        if y + size.height() > area.bottom():
            y = max(area.top(), cursor.y() - size.height() - 10)
        return QPoint(x, y)

    def _on_fade(self, value):
        self.setWindowOpacity(float(value))
        self.move(self._target + QPoint(0, int(round(4 * (1.0 - float(value))))))

    def _fit(self):
        """Resize to the content (also shrinks: adjustSize keeps a top-level
        tip at its previous, larger size)."""
        for layout in (self.frame.layout(), self.layout()):
            layout.invalidate()
            layout.activate()
        self.resize(self.sizeHint())

    def _on_grow(self, value):
        self.details.setMaximumHeight(int(value))
        self._fit()
        area = self._screen_rect(self.pos())
        overflow = self.y() + self.height() - area.bottom()
        if overflow > 0:  # keep the opened tip on screen
            self._target = QPoint(self.x(), max(area.top(), self.y() - overflow))
            self.move(self._target)

    # ── tracking ──────────────────────────────────────────────────────────
    def _anchor_alive(self):
        try:
            return self.anchor is not None and self.anchor.isVisible()
        except RuntimeError:  # deleted C++ object
            return False

    def _on_tick(self):
        if not self._anchor_alive():
            self.hide_tip()
            return
        if self.pinned:
            return
        pos = QCursor.pos()
        if not self.anchor_rect.adjusted(-2, -2, 2, 2).contains(pos):
            if not _retarget(pos):
                self.hide_tip()
            return
        if self.has_more and not self.expanded and (
                QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.expand()


_tip = None


def _instance():
    global _tip
    if _tip is None:
        _tip = InfoTip()
    return _tip


def _section_rect(header, section):
    start = header.sectionViewportPosition(section)
    size = header.sectionSize(section)
    if header.orientation() == Qt.Orientation.Horizontal:
        return QRect(start, 0, size, header.height())
    return QRect(0, start, header.width(), size)


def lookup(widget, pos):
    """(text, rect in widget coordinates) of the tip at `pos` on `widget`,
    or None. Handles header sections and item view cells."""
    parent = widget.parentWidget()
    if isinstance(parent, QHeaderView) and widget is parent.viewport():
        section = parent.logicalIndexAt(pos)
        if section < 0 or parent.model() is None:
            return None
        text = parent.model().headerData(section, parent.orientation(), Qt.ItemDataRole.ToolTipRole)
        return (str(text), _section_rect(parent, section)) if text else None
    if isinstance(parent, QAbstractItemView) and widget is parent.viewport():
        index = parent.indexAt(pos)
        if not index.isValid():
            return None
        text = index.data(Qt.ItemDataRole.ToolTipRole)
        return (str(text), parent.visualRect(index)) if text else None
    text = widget.toolTip()
    return (text, widget.rect()) if text else None


def _global_rect(widget, rect):
    return QRect(widget.mapToGlobal(rect.topLeft()), rect.size())


def _retarget(global_pos):
    """The pointer left the tip's area: if it's over another tip, swap to it
    at once (no second hover delay). True when it swapped."""
    if is_quiet():
        return False
    widget = QApplication.widgetAt(global_pos)
    tip_widget = _instance()
    while widget is not None and widget is not tip_widget:
        found = lookup(widget, widget.mapFromGlobal(global_pos))
        if found:
            tip_widget.show_tip(global_pos, found[0], widget, _global_rect(widget, found[1]))
            return True
        if widget.isWindow():
            return False
        widget = widget.parentWidget()
    return False


def show_text(global_pos, text, widget, rect=None):
    """Drop-in for QToolTip.showText: `rect` (widget coordinates) is the area
    the tip belongs to (default: the whole widget)."""
    if not text:
        hide_text()
        return
    _instance().show_tip(global_pos, text, widget, _global_rect(widget, rect or widget.rect()))


def hide_text():
    if _tip is not None and not _tip.pinned:
        _tip.hide_tip()


_quiet_until = 0.0


def quiet(seconds):
    """No hover tips for `seconds` (and any open one closes): after a click
    whose result shows on the button, the cursor resting on the next button
    (or where a menu just closed) mustn't pop a tip over it."""
    global _quiet_until
    _quiet_until = max(_quiet_until, time.monotonic() + seconds)
    if _tip is not None:
        _tip.hide_tip()


def is_quiet():
    return time.monotonic() < _quiet_until


def is_visible():
    return _tip is not None and _tip.isVisible()


class _Filter(QObject):
    SWALLOW_S = 0.6  # the right-click that opened details opens no context menu

    def __init__(self, parent=None):
        super().__init__(parent)
        self._swallow_until = 0.0

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.ToolTip and isinstance(obj, QWidget):
            if is_quiet():
                return True  # swallowed: no tip, and no native one either
            found = lookup(obj, event.pos())
            if not found:
                return False  # let it bubble to the parent
            _instance().show_tip(event.globalPos(), found[0], obj, _global_rect(obj, found[1]))
            return True
        if time.monotonic() < self._swallow_until:
            if kind == QEvent.Type.ContextMenu or (
                    kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.RightButton):
                return True
        if _tip is None or not _tip.isVisible():
            return False
        if kind == QEvent.Type.MouseButtonPress:
            right = event.button() == Qt.MouseButton.RightButton
            if right and (_tip.pinned or _tip.anchor_rect.contains(QCursor.pos())) and _tip.advance():
                self._swallow_until = time.monotonic() + self.SWALLOW_S
                return True
            _tip.hide_tip()
        elif kind == QEvent.Type.Wheel:
            if not _tip.pinned:
                _tip.hide_tip()
        elif kind == QEvent.Type.WindowDeactivate:
            _tip.hide_tip()
        elif kind == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Shift:
                _tip.expand()
            else:
                _tip.hide_tip()
        return False


_filter = None


def install(app=None):
    """Route every tooltip in `app` through InfoTip (once)."""
    global _filter
    app = app or QApplication.instance()
    if app is None or _filter is not None:
        return
    _filter = _Filter(app)
    app.installEventFilter(_filter)


# ── hints ──────────────────────────────────────────────────────────────────
HINTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ui_hints.json")


def _hint_counts():
    try:
        with open(HINTS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _bump_hint(key):
    data = _hint_counts()
    data[key] = int(data.get(key, 0) or 0) + 1
    try:
        with open(HINTS_FILE, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
    except OSError:
        pass


class HintLabel(QLabel):
    """Faint how-to text, hidden by default. reveal() fades it in while the
    hint is still new (shown fewer than `limit` times) or `always` (e.g. the
    user has hovered without acting for a while); used() fades it out and
    counts it as learned."""

    def __init__(self, text, key, parent=None, limit=3):
        super().__init__(text, parent)
        self.key = key
        self.limit = limit
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: self._effect.setOpacity(float(v)))
        self._shown = False
        self._counted = False

    def is_new(self):
        return int(_hint_counts().get(self.key, 0) or 0) < self.limit

    def _fade_to(self, value):
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(value)
        self._anim.start()

    def reveal(self, always=False):
        if self._shown or not (always or self.is_new()):
            return
        self._shown = True
        self._fade_to(1.0)

    def conceal(self):
        if self._shown:
            self._shown = False
            self._fade_to(0.0)

    def attach(self, *widgets):
        """Reveal while the pointer is over any of `widgets` (if still new)."""
        for widget in widgets:
            widget.installEventFilter(self)
        return self

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Enter:
            self.reveal()
        elif event.type() == QEvent.Type.Leave:
            self.conceal()
        return False

    def used(self):
        """The user did the thing: hide, and count one use toward `limit`."""
        if not self._counted:
            self._counted = True
            _bump_hint(self.key)
        self.conceal()
