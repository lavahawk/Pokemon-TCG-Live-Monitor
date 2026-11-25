"""The Replay tab's timeline: a wide scrub bar under the replay site with the
game's big moments marked on it.

The replay itself is ptcglreplay.com in a web view. Its own slider is small
(about 250 px for 200+ actions); this bar spans the window, steps one action
at a time, and marks the highlights read from the site's action log:

  KO       "... was Knocked Out!"
  Prize    "... took 1 Prize card(s)"
  Attack   "<Pokemon> used <attack> on ... for 120 damage" / "damage counters"
  Evolve   "evolved X into Y" / "Evolved X into Y"
  Turns    "Turn 8 - 22lava44's Turn" (the coloured lane on top, per player)

Numbers are the site's: action n in its log is slider value n.
"""

import re

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolTip, QVBoxLayout, QWidget

TURN_RE = re.compile(r"^Turn (\d+) - (.+?)'s Turn", re.I)

KINDS = {
    # kind: (label, colour, lane: -1 above the line, +1 below, importance)
    "ko": ("Knock Out", QColor(239, 83, 80), -1, 4),
    "prize": ("Prize taken", QColor(249, 196, 61), -1, 3),
    "attack": ("Attack", QColor(255, 138, 76), 1, 2),
    "evolve": ("Evolution", QColor(102, 187, 106), 1, 1),
}
HIGHLIGHTS = ("ko", "prize", "attack", "evolve")


def classify(text):
    """The highlight kind of one action line, or None."""
    t = (text or "").strip()
    if re.search(r"was Knocked Out", t, re.I):
        return "ko"
    if re.search(r"took \d+ Prize card", t, re.I):
        return "prize"
    if re.search(r"\bused\b.*(for \d+ damage|damage counters)", t, re.I):
        return "attack"
    if re.search(r"\bevolved\b.+\binto\b", t, re.I):
        return "evolve"
    return None


def parse_actions(actions):
    """[(number, text)] -> {"events": [(n, kind, text)], "turns": [(n, turn, player)]}"""
    events, turns = [], []
    for number, text in actions:
        m = TURN_RE.match(text or "")
        if m:
            turns.append((int(number), int(m.group(1)), m.group(2).strip()))
            continue
        kind = classify(text)
        if kind:
            events.append((int(number), kind, text))
    return {"events": events, "turns": turns}


def short(text, n=90):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


class TimelineTrack(QWidget):
    """The painted bar: turn lane, highlight markers, playhead. Click or drag
    to scrub; the wheel and arrow keys step one action."""

    seek = Signal(int)
    PAD = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(74)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.max = 0
        self.value = 0
        self.texts = {}
        self.events = []
        self.turns = []
        self.me = ""
        self._hover = None
        self._dragging = False

    # ── data ──
    def set_data(self, actions, me=""):
        self.texts = {int(n): t for n, t in actions}
        parsed = parse_actions(actions)
        self.events = parsed["events"]
        self.turns = parsed["turns"]
        self.me = (me or "").lower()
        self.update()

    def set_position(self, value, maximum):
        value, maximum = int(value), max(0, int(maximum))
        if (value, maximum) != (self.value, self.max):
            self.value, self.max = value, maximum
            self.update()

    def turn_at(self, n):
        current = None
        for start, turn, player in self.turns:
            if start <= n:
                current = (turn, player)
            else:
                break
        return current

    # ── geometry ──
    def _x(self, n):
        span = max(1, self.max)
        return self.PAD + (self.width() - 2 * self.PAD) * (n / span)

    def _n(self, x):
        span = max(1, self.max)
        frac = (x - self.PAD) / max(1, self.width() - 2 * self.PAD)
        return int(round(min(1.0, max(0.0, frac)) * span))

    def _event_near(self, pos, radius=8):
        best = None
        for n, kind, text in self.events:
            x = self._x(n)
            lane = KINDS[kind][2]
            y = self._line_y() + lane * 13
            d = abs(pos.x() - x) + abs(pos.y() - y) * 0.5
            if d <= radius and (best is None or d < best[0] or
                                (d == best[0] and KINDS[kind][3] > KINDS[best[2]][3])):
                best = (d, n, kind, text)
        return best

    def _line_y(self):
        return 46

    def _player_colour(self, player):
        if self.me and player.lower() == self.me:
            return QColor(74, 159, 216)
        return QColor(186, 104, 200)

    # ── input ──
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        self._dragging = True
        near = self._event_near(event.position())
        self.seek.emit(near[1] if near else self._n(event.position().x()))

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._dragging:
            self.seek.emit(self._n(pos.x()))
        near = self._event_near(pos)
        n = near[1] if near else self._n(pos.x())
        self._hover = n
        if self.max:
            text = self.texts.get(n, "")
            turn = self.turn_at(n)
            head = f"Action {n}" + (f" · Turn {turn[0]} ({turn[1]})" if turn else "")
            if near:
                head = f"{KINDS[near[2]][0]} · {head}"
            QToolTip.showText(event.globalPosition().toPoint(), f"<b>{head}</b><br>{short(text) or '&nbsp;'}", self)
        self.update()

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def wheelEvent(self, event):
        step = -1 if event.angleDelta().y() > 0 or event.angleDelta().x() > 0 else 1
        self.seek.emit(min(self.max, max(0, self.value + step)))

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = -1 if key == Qt.Key.Key_Left else 1
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                target = self.parent().next_highlight(step) if hasattr(self.parent(), "next_highlight") else None
                if target is not None:
                    self.seek.emit(target)
                return
            self.seek.emit(min(self.max, max(0, self.value + step)))
        elif key == Qt.Key.Key_Home:
            self.seek.emit(0)
        elif key == Qt.Key.Key_End:
            self.seek.emit(self.max)
        else:
            super().keyPressEvent(event)

    # ── paint ──
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        left, right = self.PAD, w - self.PAD
        line_y = self._line_y()

        # turn lane: one block per turn, coloured by whose turn it is
        lane = QRectF(left, 4, right - left, 14)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 12))
        p.drawRoundedRect(lane, 4, 4)
        small = QFont(self.font())
        small.setPointSizeF(max(6.5, small.pointSizeF() * 0.78))
        p.setFont(small)
        for i, (start, turn, player) in enumerate(self.turns):
            end = self.turns[i + 1][0] if i + 1 < len(self.turns) else self.max
            x0, x1 = self._x(start), self._x(end)
            colour = self._player_colour(player)
            colour.setAlpha(150 if self.turn_at(self.value) and self.turn_at(self.value)[0] == turn else 70)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colour)
            p.drawRoundedRect(QRectF(x0 + 0.5, 5, max(1.0, x1 - x0 - 1), 12), 3, 3)
            if x1 - x0 >= 22:
                p.setPen(QColor(240, 244, 250, 210))
                p.drawText(QRectF(x0, 5, x1 - x0, 12), Qt.AlignmentFlag.AlignCenter, f"T{turn}")

        # the line, the played part, and a tick per action when there's room
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(QRectF(left, line_y - 3, right - left, 6), 3, 3)
        if self.max:
            p.setBrush(QColor(74, 159, 216, 170))
            p.drawRoundedRect(QRectF(left, line_y - 3, self._x(self.value) - left, 6), 3, 3)
            px_per = (right - left) / max(1, self.max)
            if px_per >= 4:
                p.setPen(QPen(QColor(255, 255, 255, 40), 1))
                for n in range(self.max + 1):
                    x = self._x(n)
                    p.drawLine(QPointF(x, line_y + 4), QPointF(x, line_y + 7))
            for start, _turn, _player in self.turns:
                x = self._x(start)
                p.setPen(QPen(QColor(255, 255, 255, 70), 1))
                p.drawLine(QPointF(x, line_y - 6), QPointF(x, line_y + 6))

        # markers, least important first so a KO sits on top
        for n, kind, _text in sorted(self.events, key=lambda e: KINDS[e[1]][3]):
            self._marker(p, self._x(n), line_y + KINDS[kind][2] * 13, kind, played=n <= self.value)

        # hover line
        if self._hover is not None and self.max:
            x = self._x(self._hover)
            p.setPen(QPen(QColor(255, 255, 255, 60), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, 20), QPointF(x, self.height() - 4))

        # playhead
        if self.max:
            x = self._x(self.value)
            p.setPen(QPen(QColor(235, 243, 252), 2))
            p.drawLine(QPointF(x, 20), QPointF(x, self.height() - 6))
            p.setPen(QPen(QColor(74, 159, 216), 2))
            p.setBrush(QColor(235, 243, 252))
            p.drawEllipse(QPointF(x, line_y), 7, 7)
        p.end()

    @staticmethod
    def _marker(p, x, y, kind, played):
        colour = QColor(KINDS[kind][1])
        if not played:
            colour.setAlpha(140)
        p.setPen(QPen(QColor(13, 20, 31, 220), 1.5))
        p.setBrush(colour)
        if kind == "ko":
            p.drawEllipse(QPointF(x, y), 6.5, 6.5)
            p.setPen(QPen(QColor(13, 20, 31), 1.8))
            p.drawLine(QPointF(x - 2.6, y - 2.6), QPointF(x + 2.6, y + 2.6))
            p.drawLine(QPointF(x - 2.6, y + 2.6), QPointF(x + 2.6, y - 2.6))
        elif kind == "prize":
            p.drawPolygon(QPolygonF([QPointF(x, y - 6.5), QPointF(x + 5.5, y), QPointF(x, y + 6.5), QPointF(x - 5.5, y)]))
        elif kind == "attack":
            path = QPainterPath()
            path.moveTo(x, y - 5.5)
            path.lineTo(x + 5, y + 4.5)
            path.lineTo(x - 5, y + 4.5)
            path.closeSubpath()
            p.drawPath(path)
        else:
            p.drawEllipse(QPointF(x, y), 4, 4)


class ReplayTimeline(QWidget):
    """The bar plus its controls: highlight jumps, single steps, where you
    are, and a legend. seek(int) asks the replay to show that action."""

    seek = Signal(int)

    STYLE = """
        QWidget#replayTimeline { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07);
                                 border-radius: 10px; }
        QPushButton#timelineBtn { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);
                                  border-radius: 6px; color: rgba(235,242,250,0.88); font-size: 11px; padding: 3px 9px; }
        QPushButton#timelineBtn:hover { background: rgba(74,159,216,0.22); border-color: rgba(74,159,216,0.45); }
        QPushButton#timelineBtn:disabled { color: rgba(235,242,250,0.30); }
        QLabel#timelineNow { color: rgba(240,244,250,0.92); font-size: 12px; background: transparent; }
        QLabel#timelineLegend { color: rgba(168,182,204,0.85); font-size: 10px; background: transparent; }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("replayTimeline")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(self.STYLE)
        col = QVBoxLayout(self)
        col.setContentsMargins(10, 8, 10, 6)
        col.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.prev_hl = self._button("◀ Highlight", "Previous highlight (Shift+←)", lambda: self._jump(-1))
        self.prev_btn = self._button("◀", "Back one action (←)", lambda: self._step(-1))
        self.next_btn = self._button("▶", "Forward one action (→)", lambda: self._step(1))
        self.next_hl = self._button("Highlight ▶", "Next highlight (Shift+→)", lambda: self._jump(1))
        for b in (self.prev_hl, self.prev_btn, self.next_btn, self.next_hl):
            row.addWidget(b)
        self.now = QLabel("")
        self.now.setObjectName("timelineNow")
        self.now.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(self.now, 1)
        legend = " ".join(
            f"<span style='color:{KINDS[k][1].name()}'>{sym}</span>&nbsp;{KINDS[k][0]}&nbsp;&nbsp;"
            for k, sym in (("ko", "●"), ("prize", "◆"), ("attack", "▲"), ("evolve", "•")))
        self.legend = QLabel(legend)
        self.legend.setObjectName("timelineLegend")
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(self.legend)
        self._row = row
        col.addLayout(row)
        self.track = TimelineTrack(self)
        self.track.seek.connect(self.seek)
        col.addWidget(self.track)

    def _button(self, text, tip, slot):
        b = QPushButton(text)
        b.setObjectName("timelineBtn")
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(slot)
        return b

    def add_button(self, text, tip, slot):
        """An extra button at the end of the top row."""
        b = self._button(text, tip, slot)
        self._row.addWidget(b)
        return b

    # ── data in ──
    def set_actions(self, actions, me=""):
        self.track.set_data(actions, me)
        self._refresh()

    def set_position(self, value, maximum):
        self.track.set_position(value, maximum)
        self._refresh()

    def has_actions(self):
        return bool(self.track.texts)

    # ── navigation ──
    def next_highlight(self, direction):
        """The next (1) or previous (-1) KO, prize, attack or evolution."""
        value = self.track.value
        marks = sorted({n for n, _k, _t in self.track.events})
        if direction > 0:
            later = [n for n in marks if n > value]
            return later[0] if later else None
        earlier = [n for n in marks if n < value]
        return earlier[-1] if earlier else None

    def _jump(self, direction):
        target = self.next_highlight(direction)
        if target is not None:
            self.seek.emit(target)

    def _step(self, direction):
        self.seek.emit(min(self.track.max, max(0, self.track.value + direction)))

    def _refresh(self):
        t = self.track
        n = t.value
        turn = t.turn_at(n)
        where = f"<b>Action {n}</b> / {t.max}" + (f" &nbsp;·&nbsp; Turn {turn[0]} ({turn[1]})" if turn else "")
        text = t.texts.get(n, "")
        kind = classify(text)
        if kind:
            text = f"<span style='color:{KINDS[kind][1].name()}'>{short(text)}</span>"
        else:
            text = short(text)
        self.now.setText(f"{where}{' &nbsp;—&nbsp; ' + text if text else ''}")
        self.prev_btn.setEnabled(n > 0)
        self.next_btn.setEnabled(n < t.max)
        self.prev_hl.setEnabled(self.next_highlight(-1) is not None)
        self.next_hl.setEnabled(self.next_highlight(1) is not None)

    def keyPressEvent(self, event):
        self.track.keyPressEvent(event)
