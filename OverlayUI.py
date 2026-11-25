"""
Minimal Game Overlay for Pokemon TCG Live Monitor (version: version.py)
Ultra-compact, professional overlay that follows the game and allows click-through
"""

import sys
import os
import math
import random
import threading
import time
import webbrowser
import win32gui
import win32process
import win32con
import psutil
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QRectF, QPoint, QPointF
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage, QPen, QFont
from BattleDatabase import BattleDatabase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "Logs")
GAME_SESSION_FILE = os.path.join(LOG_DIR, ".game_session")  # written by the monitor on game start
SESSION_PROMPT_WINDOW_S = 120  # offer the W-L reset only this soon after the game started
SESSION_PROMPT_LINGER_MS = 10000
DECK_FLAGS_FILE = os.path.join(BASE_DIR, ".deck_flags.json")  # starred / ignored decks (dashboard)


def ignored_decks():
    """Decks marked Ignore on the dashboard: left out of today's W-L."""
    try:
        import json
        with open(DECK_FLAGS_FILE, "r", encoding="utf-8") as handle:
            return [str(d) for d in (json.load(handle) or {}).get("ignored", [])]
    except Exception:
        return []


def _overlay_setting(key, default):
    try:
        from app_settings import load_app_settings
        return load_app_settings().get(key, default)
    except Exception:
        return default


class FadingPopup(QWidget):
    """Frameless popup that can fade itself out after `linger_ms` (hovering
    keeps it; leaving restarts a shorter countdown). linger_ms=None = stays."""

    def __init__(self, linger_ms=None, opacity=0.92):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._linger = linger_ms
        self._opacity = opacity
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.fade_out)
        self._anim = None
        self.setWindowOpacity(opacity)

    def _animate(self, start, end, ms, done=None):
        if self._anim is not None:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(ms)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic if end > start else QEasingCurve.Type.InCubic)
        if done:
            self._anim.finished.connect(done)
        self._anim.start()

    def show_animated(self):
        if self._linger:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setWindowOpacity(0.0)
            self.show()
            self._animate(0.0, self._opacity, 260)
            self._timer.start(self._linger)
        else:
            self.show()

    def fade_out(self):
        self._animate(self.windowOpacity(), 0.0, 700, self.close)

    def enterEvent(self, event):
        if self._linger:
            self._timer.stop()
            if self.windowOpacity() < self._opacity:
                self._animate(self.windowOpacity(), self._opacity, 150)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._linger and self.isVisible():
            self._timer.start(3500)
        super().leaveEvent(event)

# --- DEBUG LOGGING (internal only) ---
import datetime as _dt
_DBG_FILE = os.path.join(BASE_DIR, ".overlay_debug.log")
_DBG_MAX_BYTES = 1_000_000


def _dbg(msg):
    """Small rotating debug log (was unbounded: 11 MB+, BUG-019)."""
    try:
        if os.path.exists(_DBG_FILE) and os.path.getsize(_DBG_FILE) > _DBG_MAX_BYTES:
            os.replace(_DBG_FILE, _DBG_FILE + ".1")
        line = f"[{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] {msg}\n"
        with open(_DBG_FILE, "a", encoding="utf-8") as _f:
            _f.write(line)
    except Exception:
        pass
# --- END DEBUG ---


# Pixel art of the mini GUI's ball, 9x9: K outline, H highlight, T top colour,
# D top shade, B button, W white, S white shade.
BALL_ART = (
    "..KKKKK..",
    ".KHTTTDK.",
    "KHTTTTTDK",
    "KTTKKKTDK",
    "KKKKBKKKK",
    "KWWKKKWSK",
    "KWWWWWWSK",
    ".KSWWWSK.",
    "..KKKKK..",
)
BALL_COLORS = {  # league -> (top, top shade)
    "nest": ("#9CC344", "#5C7C28"),
    "quick": ("#4A9FD8", "#2B5F8C"),
    "poke": ("#E53935", "#A82222"),
    "great": ("#1976D2", "#0D47A1"),
    "ultra": ("#F9A825", "#C77A10"),
    "master": ("#7B1FA2", "#4A148C"),
}


def _ball_art(ball_type):
    """The ball at its own pixel size (9x9), one QImage pixel per art pixel."""
    top, shade = BALL_COLORS.get(ball_type, BALL_COLORS["poke"])
    palette = {"K": QColor("#141414"), "T": QColor(top), "D": QColor(shade), "H": QColor(top).lighter(150),
               "W": QColor("#F5F5F5"), "S": QColor("#C3C8CF"), "B": QColor("#FFFFFF")}
    art = QImage(len(BALL_ART[0]), len(BALL_ART), QImage.Format.Format_ARGB32_Premultiplied)
    art.fill(Qt.GlobalColor.transparent)
    for y, row in enumerate(BALL_ART):
        for x, key in enumerate(row):
            if key in palette:
                art.setPixelColor(x, y, palette[key])
    return art


_ball_art_cache = {}


def _turned_ball(ball_type, angle):
    """The 9x9 sprite turned by `angle` degrees, still on its pixel grid,
    plus one art pixel each side (11x9). A circle stays a circle: the
    outline is fixed and only the pattern inside turns (RotSprite-style:
    enlarge 8x, rotate with nearest sampling, sample back down), and the
    ball rolls a pixel at the steepest tilts, rocking on its base."""
    key = (ball_type, int(round(angle)))
    if key in _ball_art_cache:
        return _ball_art_cache[key]
    art = _ball_art(ball_type)
    size, up = len(BALL_ART), 8
    big = art.scaled(size * up, size * up, Qt.AspectRatioMode.IgnoreAspectRatio,
                     Qt.TransformationMode.FastTransformation)
    turned = QImage(big.size(), QImage.Format.Format_ARGB32_Premultiplied)
    turned.fill(Qt.GlobalColor.transparent)
    p = QPainter(turned)  # no smoothing: nearest pixels only
    p.translate(size * up / 2.0, size * up / 2.0)
    p.rotate(key[1])
    p.translate(-size * up / 2.0, -size * up / 2.0)
    p.drawImage(0, 0, big)
    p.end()

    def inside(x, y):
        return 0 <= x < size and 0 <= y < size and art.pixelColor(x, y).alpha() > 0
    outline = QColor("#141414")
    roll = max(-1, min(1, int(round(math.sin(math.radians(key[1])) * 4))))
    out = QImage(size + 2, size, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    for y in range(size):
        for x in range(size):
            if not inside(x, y):
                continue
            edge = not all(inside(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            color = turned.pixelColor(x * up + up // 2, y * up + up // 2)
            out.setPixelColor(1 + x + roll, y, outline if edge or color.alpha() == 0 else color)
    if len(_ball_art_cache) > 400:
        _ball_art_cache.clear()
    _ball_art_cache[key] = out
    return out


def create_pokeball_icon(ball_type="poke", dpr=1.0, angle=0.0, scale=1.0):
    """The league's ball as chunky pixel art: each art pixel is a whole block
    of screen pixels (2x2 at 150 %), never smoothed, about 12 logical px tall.
    angle: tilt in degrees (the shake of a ball with something inside); it
    turns on its pixel grid (_turned_ball), so it stays pixel art."""
    block = max(1, int(round(12 * scale * dpr / len(BALL_ART))))
    art = _turned_ball(ball_type, angle)
    big = art.scaled(art.width() * block, art.height() * block, Qt.AspectRatioMode.IgnoreAspectRatio,
                     Qt.TransformationMode.FastTransformation)
    pixmap = QPixmap.fromImage(big)
    pixmap.setDevicePixelRatio(max(1.0, dpr))
    return pixmap


class PixelBall(QLabel):
    """The mini GUI's ball: paints its pixel art itself, at whole screen
    pixels (a QLabel centring a pixmap can land it between pixels at 150 %
    and smear it), centred on the capitals of the text beside it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix = None
        self._y = 0.0

    def set_ball(self, pix, text_label):
        """Show `pix` centred on `text_label`'s capitals; this label is as
        tall as the text label, so the layout lines both up alike."""
        from PySide6.QtGui import QFontMetricsF
        text_label.ensurePolished()  # its stylesheet font, not the default
        fm = QFontMetricsF(text_label.font())
        # The text's natural height, never text_label.height(): before the
        # layout has run, that is Qt's default 480 px, and a ball box that
        # tall stretched the whole mini GUI. Both boxes are this tall and the
        # layout centres both in the row, so their middles line up.
        height = max(1, text_label.sizeHint().height())
        ratio = pix.devicePixelRatio() or 1.0
        width = int(math.ceil(pix.width() / ratio - 0.01))
        caps_middle = (height - fm.height()) / 2.0 + fm.ascent() - fm.capHeight() / 2.0  # QLabel centres its line
        self._pix, self._y = pix, caps_middle - pix.height() / ratio / 2.0
        if (self.width(), self.height()) != (width, height):
            self.setFixedSize(width, height)
        self.update()

    def paintEvent(self, _event):
        if self._pix is None:
            return
        dpr = self.devicePixelRatioF() or 1.0
        origin = self.mapTo(self.window(), QPoint(0, 0))
        x = round(origin.x() * dpr) / dpr - origin.x()  # snap to the window's screen pixels
        y = round((origin.y() + self._y) * dpr) / dpr - origin.y()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawPixmap(QPointF(x, y), self._pix)
        p.end()


def get_league_from_elo(elo):
    """Which league ball to show for a ladder rank (thresholds in leagues.py)."""
    from leagues import league_for_rank
    return league_for_rank(elo)


class ChatLinesView(QWidget):
    """The idle chat: a few outlined lines painted straight over the game
    (bold text with a black stroke, readable on any card art), each with its
    own fade. With nothing to show it draws a small speech-bubble icon, the
    spot to rest the mouse on."""

    PAD = 2
    GAP = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QFont
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.font_main = QFont("Segoe UI")
        self.font_main.setPixelSize(13)
        self.font_main.setWeight(QFont.Weight.DemiBold)
        self.font_action = QFont("Segoe UI")
        self.font_action.setPixelSize(12)
        self.font_action.setWeight(QFont.Weight.Medium)
        self.lines = []          # [(kind, text, sender, alpha)]
        self.hot = None          # QRectF of what is drawn (hover target)
        self._rows = []
        self._height = 0

    def set_lines(self, lines, width):
        self.lines = lines
        self._layout(width)
        self.setFixedHeight(self._height)
        self.update()

    def _layout(self, width):
        """Word-wrap every line into rows of (x, segments, font)."""
        from PySide6.QtGui import QFontMetricsF
        self._rows = []
        y = self.PAD
        avail = width - 2 * self.PAD
        left = right = None
        for kind, text, sender, alpha in self.lines:
            font = self.font_action if kind == "action" else self.font_main
            fm = QFontMetricsF(font)
            colors = {
                "action": (212, 218, 228), "own": (196, 220, 255), "sent": (196, 220, 255),
                "sending": (150, 168, 196), "failed": (255, 138, 138), "them": (245, 248, 252),
            }
            tokens = []
            if kind == "them" and sender:
                tokens += [(w, (240, 198, 116)) for w in sender.split()]
            tokens += [(w, colors.get(kind, (245, 248, 252))) for w in text.split()]
            if kind == "sending":
                tokens.append(("…", colors["sending"]))
            space = fm.horizontalAdvance(" ")
            rows, cur, cur_w = [], [], 0.0
            for word, rgb in tokens:
                w = fm.horizontalAdvance(word)
                need = w if not cur else cur_w + space + w
                if cur and need > avail:
                    rows.append((cur, cur_w))
                    cur, cur_w = [], 0.0
                    need = w
                cur.append((word, rgb))
                cur_w = need
            if cur:
                rows.append((cur, cur_w))
            for words, row_w in rows:
                if kind in ("own", "sent", "sending", "failed"):
                    x = width - self.PAD - row_w
                elif kind == "action":
                    x = (width - row_w) / 2
                else:
                    x = self.PAD
                self._rows.append((x, y + fm.ascent(), words, font, alpha, space))
                left = x if left is None else min(left, x)
                right = x + row_w if right is None else max(right, x + row_w)
                y += fm.height()
            y += self.GAP
        if self._rows:
            self._height = int(y + self.PAD)
            self.hot = QRectF(left - 4, 0, (right - left) + 8, self._height)
        else:
            # Nothing to read: a small bubble at the right edge.
            self._height = 22
            self.hot = QRectF(width - 30, 0, 30, 22)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainterPath, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._rows:
            w = self.width()
            path = QPainterPath()
            path.addRoundedRect(QRectF(w - 25, 3, 20, 13), 4, 4)
            tail = QPainterPath()
            tail.moveTo(w - 19, 15.5)
            tail.lineTo(w - 21, 20)
            tail.lineTo(w - 14, 15.5)
            path = path.united(tail)
            p.setPen(QPen(QColor(0, 0, 0, 200), 2.2))
            p.setBrush(QColor(245, 248, 252, 190))
            p.drawPath(path)
            p.end()
            return
        for x, baseline, words, font, alpha, space in self._rows:
            if alpha <= 0.01:
                continue
            cx = x
            from PySide6.QtGui import QFontMetricsF
            fm = QFontMetricsF(font)
            for word, rgb in words:
                path = QPainterPath()
                path.addText(QPointF(cx, baseline), font, word)
                pen = QPen(QColor(0, 0, 0, int(235 * alpha)), 3.4)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.strokePath(path, pen)
                p.fillPath(path, QColor(rgb[0], rgb[1], rgb[2], int(255 * alpha)))
                cx += fm.horizontalAdvance(word) + space
        p.end()


class DeckIconWindow(QWidget):
    """A small three-card icon just above the chat's top-right corner, drawn
    like the chat's speech bubble (light fill, dark outline, theme colours).
    Shown once this match's opponent decklist is in; click it to bring the
    decklist window back up."""

    W, H = 34, 24

    def __init__(self, anchor, available, on_click):
        super().__init__()
        self.setWindowTitle("OpponentDeckIcon")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Opponent's decklist")
        self.anchor = anchor          # the chat window
        self.available = available    # () -> bool: a list for this match?
        self.on_click = on_click
        self._hover = False
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def refresh(self):
        try:
            want = bool(self.anchor is not None and self.anchor.isVisible() and self.available())
        except Exception:
            want = False
        if want:
            self.reposition()
            if not self.isVisible():
                self.show()
            self.raise_()
        elif self.isVisible():
            self.hide()

    def reposition(self):
        if self.anchor is None:
            return
        geo = self.anchor.geometry()
        self.move(geo.x() + geo.width() - self.W, geo.y() - self.H)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.on_click:
            self.on_click()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(245, 248, 252, 245 if self._hover else 190)
        pen = QPen(QColor(0, 0, 0, 200), 2.2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        # Three cards fanned like a hand, back to front, bottom-right aligned
        # with the chat bubble below.
        cw, ch = 10.5, 14.5
        cx, cy = self.W - 15, self.H - 5
        for angle, dx in ((-18, -5.5), (0, 0), (18, 5.5)):
            p.save()
            p.translate(cx + dx, cy)
            p.rotate(angle)
            card = QPainterPath()
            card.addRoundedRect(QRectF(-cw / 2, -ch, cw, ch), 2.2, 2.2)
            p.setPen(pen)
            p.setBrush(fill)
            p.drawPath(card)
            p.restore()
        p.end()


class LimitlessChatWindow(QWidget):
    """Limitless match chat above the mini GUI, usable mid-game.

    Idle: no box, just the newest few messages as outlined text over the
    game; each stays bright HOLD_S then fades out over FADE_S (older lines a
    bit dimmer). When everything has faded only a small speech-bubble icon is
    left. Click-through throughout.

    Rest the mouse on the text or the icon (HOVER_DWELL_MS) and it opens: a
    light dark wash, round + opponent, the whole conversation and a message
    box. Click it, type, Enter sends to the match chat on Limitless and hands
    the keyboard back to the game (Esc too).
    """

    WIDTH = 270
    MAX_BODY_H = 180         # the whole conversation while hovered
    MAX_MESSAGES = 30
    IDLE_LINES = 3           # newest messages shown while you play
    HOLD_S = 20.0            # a message stays bright this long
    FADE_S = 8.0             # ...then fades out over this long
    HOVER_DWELL_MS = 300
    HEAD_H = 16
    INPUT_H = 24

    STYLE = """
        QFrame#chatPanel { background: transparent; border: none; border-radius: 7px; }
        QFrame#chatPanel[open="true"] { background: rgba(8,11,16,0.62); }
        QLabel#chatTitle { color: rgba(240,198,116,0.95); font-family: 'Segoe UI', Arial; font-size: 9px;
                           font-weight: 700; letter-spacing: 0.6px; background: transparent; }
        QTextBrowser { background: transparent; border: none; color: #F2F6FA;
                       font-family: 'Segoe UI', Arial; font-size: 12px; }
        QLineEdit#chatInput { background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.22);
                              border-radius: 4px; color: #FFFFFF; padding: 2px 6px;
                              font-family: 'Segoe UI', Arial; font-size: 11px; }
        QLineEdit#chatInput:focus { border: 1px solid rgba(240,198,116,0.80); }
        QToolButton#chatSend { background: transparent; border: none; color: rgba(236,242,252,0.80);
                               font-weight: 700; font-size: 10px; padding: 0 4px; }
        QToolButton#chatSend:hover { color: #FFFFFF; }
        QScrollBar:vertical { background: transparent; width: 5px; margin: 0; }
        QScrollBar::handle:vertical { background: rgba(255,255,255,0.25); border-radius: 2px; min-height: 18px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
    """

    def __init__(self):
        super().__init__()
        from PySide6.QtWidgets import QTextBrowser, QToolButton, QLineEdit
        self.setWindowTitle("LimitlessChat")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(self.WIDTH)
        self.messages = []
        self.pending = []          # [{text, failed, sent, at, error}] typed here
        self.own_names = set()     # this player's names (app username + Limitless's "self")
        self.opponent = ""
        self._hovered = False
        self._hover_since = None
        self._click_through = None
        self._newest = None
        self._shown_key = None
        self.on_send = None        # callback(text), set by the overlay
        self.suppressed = False    # True while the game is minimized
        self.retired = False       # True a few minutes after the round ended

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.panel = QFrame()
        self.panel.setObjectName("chatPanel")
        outer.addWidget(self.panel)
        col = QVBoxLayout(self.panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        self.title = QLabel("LIMITLESS CHAT")
        self.title.setObjectName("chatTitle")
        self.title.setFixedHeight(self.HEAD_H)
        col.addWidget(self.title)
        self.lines_view = ChatLinesView()
        col.addWidget(self.lines_view)
        self.body = QTextBrowser()
        self.body.setOpenLinks(False)
        self.body.setReadOnly(True)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                          | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.body.viewport().setAutoFillBackground(False)
        self.body.document().setDocumentMargin(2)
        col.addWidget(self.body)
        self.input_row = QWidget()
        row = QHBoxLayout(self.input_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        self.input = QLineEdit()
        self.input.setObjectName("chatInput")
        self.input.setMaxLength(300)
        self.input.setFixedHeight(self.INPUT_H)
        self.input.setPlaceholderText("Message your opponent…")
        self.input.returnPressed.connect(self._send)
        self.input.installEventFilter(self)
        row.addWidget(self.input, 1)
        self.send_btn = QToolButton()
        self.send_btn.setObjectName("chatSend")
        self.send_btn.setText("Send")
        self.send_btn.setFixedHeight(self.INPUT_H)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)
        col.addWidget(self.input_row)
        self.setStyleSheet(self.STYLE)

        self._tick = QTimer(self)
        self._tick.setInterval(80)
        self._tick.timeout.connect(self._on_tick)

    # --- click-through (WS_EX_TRANSPARENT) ------------------------------------
    def _set_click_through(self, on):
        if on == self._click_through:
            return
        self._click_through = on
        try:
            import win32api
            hwnd = int(self.winId())
            style = win32api.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED
            style = (style | win32con.WS_EX_TRANSPARENT) if on else (style & ~win32con.WS_EX_TRANSPARENT)
            win32api.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._click_through = None
        self._set_click_through(not self._hovered)
        self._tick.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._tick.stop()

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.input:
            if event.type() == QEvent.Type.MouseButtonPress:
                # A Tool window shown without activating: take the keyboard
                # from the game so typing lands in the box.
                self._take_keyboard()
            elif event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                self.input.clear()
                self._give_keyboard_back()
                return True
        return super().eventFilter(obj, event)

    def _take_keyboard(self):
        try:
            self.activateWindow()
            win32gui.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass
        self.input.setFocus()

    def _give_keyboard_back(self):
        """Back to Pokémon TCG Live so the next click or key plays the game."""
        self.input.clearFocus()
        try:
            import game_window
            hwnd = game_window.find_game_hwnd()
            if hwnd:
                win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _over_target(self, pos):
        """Is the mouse on the chat? Open: anywhere on it. Idle: only on the
        drawn text or the bubble (the rest is empty game)."""
        if self._hovered:
            return self.frameGeometry().contains(pos)
        hot = self.lines_view.hot
        if hot is None or not self.lines_view.isVisible():
            return False
        top_left = self.lines_view.mapToGlobal(QPoint(int(hot.x()), int(hot.y())))
        return (top_left.x() <= pos.x() <= top_left.x() + hot.width()
                and top_left.y() <= pos.y() <= top_left.y() + hot.height())

    def _on_tick(self):
        from PySide6.QtGui import QCursor
        now = time.monotonic()
        if self._over_target(QCursor.pos()):
            if self._hover_since is None:
                self._hover_since = now
            hovered = (now - self._hover_since) * 1000 >= self.HOVER_DWELL_MS
        else:
            self._hover_since = None
            hovered = False
        engaged = hovered or self.input.hasFocus() or bool(self.input.text())
        if engaged != self._hovered:
            self._hovered = engaged
            self._set_click_through(not engaged)
        # Failed sends stay up a while; sent ones until the page shows them
        # (or 30 s, in case the page words them differently).
        self.pending = [p for p in self.pending
                        if not ((p["failed"] and now - p["at"] > 12) or (p.get("sent") and now - p["at"] > 30))]
        self._render()  # cheap: redraws only when something changes

    # --- sending ------------------------------------------------------------------
    def _send(self):
        text = self.input.text().strip()
        if not text:
            self._give_keyboard_back()
            return
        self.input.clear()
        self.pending.append({"text": text, "failed": False, "at": time.monotonic(), "error": ""})
        self._newest = datetime.now()
        self._render()
        self._give_keyboard_back()
        if self.on_send:
            self.on_send(text)
        else:
            self.send_result(False, "Couldn't send: the Limitless page isn't loaded.", text)

    def send_result(self, ok, message="", text=None):
        """The manager's answer for a sent line."""
        for item in self.pending:
            if not item["failed"] and not item.get("sent") and (text is None or item["text"] == text):
                if ok:
                    item["sent"] = True       # Limitless took it
                else:
                    item["failed"] = True
                    item["error"] = message or "Couldn't send."
                item["at"] = time.monotonic()
                break
        self._render()

    # --- data -------------------------------------------------------------------
    def set_messages(self, messages, own_name="", title="", opponent=""):
        """messages: [{text, type, sender, ts(ISO), own}], maybe empty while a
        match is open. Returns True if a new message arrived."""
        from collections import Counter
        if own_name and own_name.strip():
            self.own_names.add(own_name.strip().lower())
        self.opponent = (opponent or "").strip()
        self.input.setPlaceholderText(f"Message {self.opponent}…" if self.opponent else "Message your opponent…")
        self.title.setText((title or "Limitless chat").upper())
        parsed = []
        for msg in messages[-self.MAX_MESSAGES:]:
            text = str(msg.get("text") or "").strip()
            if not text:
                continue
            try:
                ts = datetime.fromisoformat(str(msg.get("ts") or ""))
            except Exception:
                ts = datetime.now()
            parsed.append({"text": text, "type": str(msg.get("type") or "chat"),
                           "sender": str(msg.get("sender") or "").strip(), "ts": ts,
                           "own": bool(msg.get("own"))})
            if parsed[-1]["own"] and parsed[-1]["sender"]:
                self.own_names.add(parsed[-1]["sender"].lower())  # Limitless marks our lines
        before = Counter((m["sender"], m["text"]) for m in self.messages)
        after = Counter((m["sender"], m["text"]) for m in parsed)
        arrived = after - before
        # A line we sent showed up on the page.
        for (sender, text) in arrived:
            seen_text = text.strip().lower()
            for item in list(self.pending):
                mine = item["text"].strip().lower()
                if seen_text == mine or seen_text.endswith(" " + mine):
                    self.pending.remove(item)
                    break
        opening = not self.isVisible() and not self.suppressed and not self.retired
        self.messages = parsed
        if arrived or opening or self._newest is None:
            self._newest = datetime.now()
        self._shown_key = None
        self._render()
        if opening:
            self.show()
        if arrived or opening:
            self.raise_()
        return bool(arrived)

    def _is_own(self, msg):
        if msg.get("own"):
            return True
        sender = (msg.get("sender") or "").strip().lower()
        return bool(sender) and sender in self.own_names

    def _alpha(self, ts, now):
        age = (now - ts).total_seconds()
        if age <= self.HOLD_S:
            return 1.0
        return max(0.0, 1.0 - (age - self.HOLD_S) / self.FADE_S)

    def _lines(self, hovered):
        now = datetime.now()
        lines = []
        for msg in self.messages:
            kind = "action" if msg["type"] == "action" else ("own" if self._is_own(msg) else "them")
            lines.append([kind, msg["text"], msg["sender"], 1.0 if hovered else self._alpha(msg["ts"], now)])
        for item in self.pending:
            kind = "sent" if item.get("sent") else ("failed" if item["failed"] else "sending")
            text = item["text"] if kind != "failed" else f"{item['text']} ({item.get('error') or 'not sent'})"
            lines.append([kind, text, "", 1.0])
        if hovered:
            return lines
        lines = [l for l in lines if l[3] > 0.02][-self.IDLE_LINES:]
        n = len(lines)
        for i, l in enumerate(lines):
            l[3] *= 1.0 - (n - 1 - i) / max(1, n) * 0.4   # older lines a bit dimmer
        return lines

    def _render(self):
        hovered = self._hovered
        lines = self._lines(hovered)
        key = (hovered, tuple((l[0], l[1], l[2], round(l[3] * 20)) for l in lines))
        if key == self._shown_key:
            return
        self._shown_key = key
        if hovered:
            self._render_open(lines)
        else:
            self.lines_view.set_lines([tuple(l) for l in lines], self.WIDTH)
        self._fit()

    def _render_open(self, lines):
        import html
        rows = []
        for kind, text, sender, _a in lines:
            text = html.escape(text)
            if kind == "action":
                rows.append(f"<p align='center' style='margin:2px 0; color:#AAB4C0; font-size:11px;'><i>{text}</i></p>")
            elif kind in ("own", "sent"):
                rows.append(f"<p align='right' style='margin:2px 0; color:#C4DCFF;'>{text}</p>")
            elif kind == "failed":
                rows.append(f"<p align='right' style='margin:2px 0; color:#FF8A8A;'>{text}</p>")
            elif kind == "sending":
                rows.append(f"<p align='right' style='margin:2px 0; color:#96A8C4;'>{text} …</p>")
            else:
                who = html.escape(sender)
                name = f"<span style='color:#F0C674; font-weight:600;'>{who}</span>&nbsp; " if who else ""
                rows.append(f"<p align='left' style='margin:2px 0;'>{name}{text}</p>")
        if not rows:
            who = html.escape(self.opponent) if self.opponent else "your opponent"
            rows.append(f"<p align='left' style='margin:2px 0; color:#AAB4C0;'><i>No messages yet. "
                        f"Type below to message {who}.</i></p>")
        self.body.setHtml("".join(rows))
        bar = self.body.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _fit(self):
        open_ = self._hovered
        self.panel.setProperty("open", "true" if open_ else "false")
        self.panel.style().unpolish(self.panel)
        self.panel.style().polish(self.panel)
        self.panel.layout().setContentsMargins(*((8, 5, 6, 6) if open_ else (0, 0, 0, 0)))
        self.title.setVisible(open_)
        self.body.setVisible(open_)
        self.input_row.setVisible(open_)
        self.lines_view.setVisible(not open_)
        if open_:
            doc = self.body.document()
            doc.setTextWidth(self.WIDTH - 18)
            body_h = min(self.MAX_BODY_H, int(doc.size().height()) + 4)
            self.body.setFixedHeight(body_h)
            height = 5 + self.HEAD_H + 4 + body_h + 4 + self.INPUT_H + 6
        else:
            height = self.lines_view.height()
        self.setFixedHeight(height)
        overlay = getattr(self, "on_resized", None)
        if overlay:
            overlay()


class ChatPingGlow(QWidget):
    """A soft yellow glow that pulses just above the mini GUI when a new
    Limitless chat message arrives. Click-through, never takes focus."""

    def __init__(self):
        super().__init__()
        from PySide6.QtCore import QVariantAnimation
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._level = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(1300)
        self._anim.setStartValue(0.0)
        self._anim.setKeyValueAt(0.35, 1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(2)
        self._anim.valueChanged.connect(self._set_level)
        self._anim.finished.connect(self.hide)

    def _set_level(self, value):
        self._level = float(value)
        self.update()

    def ping(self, hud_geometry):
        self.setGeometry(hud_geometry.x() - 16, hud_geometry.y() - 22, hud_geometry.width() + 32, 30)
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.start()

    def paintEvent(self, event):
        from PySide6.QtGui import QRadialGradient
        if self._level <= 0.01:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # A flat glow centred on the mini GUI's top edge (unit circle, scaled).
        painter.translate(w / 2, h)
        painter.scale(w / 2, h)
        gradient = QRadialGradient(0, 0, 1)
        alpha = int(120 * self._level)
        gradient.setColorAt(0.0, QColor(255, 214, 90, alpha))
        gradient.setColorAt(0.55, QColor(255, 200, 60, int(alpha * 0.35)))
        gradient.setColorAt(1.0, QColor(255, 200, 60, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(-1, -1, 2, 2))
        painter.end()


class MinimalOverlay(QWidget):
    """Minimal, professional overlay that follows the game window"""
    
    def __init__(self):
        super().__init__()
        _dbg("=== OverlayUI starting ===")
        _dbg(f"BASE_DIR: {BASE_DIR}")
        self.last_log_count = 0
        self.game_hwnd = None
        self.current_rank = "--"
        self.max_rank = "--"
        self.wins = 0
        self.losses = 0
        self.parent_monitor_running = True
        self.db = BattleDatabase()  # Initialize database connection
        self.stats_window = None  # Stats dashboard window
        # Pre-build the dashboard (hidden) once the hub is up, so the first
        # click on the arrow opens it instantly.
        QTimer.singleShot(4000, self._ensure_stats_window)
        self.stats_window_tracking_suspended = False
        self.limitless_manager = None
        self.limitless_chat_state = {}
        try:
            from StatsUI import get_limitless_dashboard_manager
            self.limitless_manager = get_limitless_dashboard_manager()
            if self.limitless_manager:
                self.limitless_manager.set_overlay(self)
                self.limitless_manager.chat_state_changed.connect(self.update_limitless_chat)
        except Exception as chat_manager_error:
            _dbg(f"limitless manager hookup failed: {chat_manager_error}")
        
        _dbg("Calling init_ui()")
        self.init_ui()
        _dbg(f"init_ui() done. Widget size: {self.width()}x{self.height()}")
        _dbg("Calling load_stats()")
        self.load_stats()
        _dbg("load_stats() done")
        
        # Auto-refresh stats every 3 seconds
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.load_stats)
        self.refresh_timer.start(3000)
        _dbg("refresh_timer started (3000ms)")
        
        # Check game window position every second
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self.follow_game_window)
        self.position_timer.start(1000)
        _dbg("position_timer started (1000ms)")
        
        # Check if parent monitor is still running every 5 seconds
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.check_monitor_running)
        self.monitor_timer.start(5000)
        _dbg("monitor_timer started (5000ms)")

        # "Opponent deck" card above the mini GUI after each saved battle
        # (deck_confirm.py / deck_popup.py).
        self.deck_popup = None
        self._deck_request_mtime = None
        self.deck_timer = QTimer()
        self.deck_timer.timeout.connect(self._poll_deck_confirm)
        self.deck_timer.start(1000)
        self._session_seen = None
        self._session_prompt_due = None
        self.pet = None  # HUD buddy (pet.py), off unless overlay_pet is on
        # A decklist copied from anywhere (PTCGL's Export, a website, a
        # friend's message): a card above the HUD asks whether to import it.
        self._pending_decklist = None
        self._decklist_card = None
        try:
            QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)
        except Exception as exc:
            _dbg(f"clipboard hookup failed: {exc}")
        # Restarted from the dashboard (theme / Restart app): skip the launch
        # prompts already seen and reopen the dashboard where it was.
        import ui_restart
        self._restart_note = ui_restart.take()
        if self._restart_note:
            self._manual_notice_checked = True
            try:
                with open(GAME_SESSION_FILE, "r", encoding="utf-8") as handle:
                    self._session_seen = float(handle.read().strip() or 0)
            except (OSError, ValueError):
                pass
        _dbg("__init__ complete")
    
    def _poll_deck_confirm(self):
        self._poll_minimize_request()
        if not getattr(self, "_overlay_placed", False):
            return  # anchored popups wait until the mini GUI sits on the game window
        try:
            from deck_confirm import REQUEST_FILE, menu_seen_at, read_request
            try:
                mtime = os.path.getmtime(REQUEST_FILE)
            except OSError:
                mtime = None
            geo = self.frameGeometry()
            anchor = (geo.right() + 1, geo.top() - 6)
            if mtime != self._deck_request_mtime:
                self._deck_request_mtime = mtime
                request = read_request()
                if request:
                    if self.deck_popup is None:
                        from deck_popup import DeckConfirmPopup
                        self.deck_popup = DeckConfirmPopup(self.db, open_settings=self.open_api_key_setting)
                    self.deck_popup.offer(request, anchor)
                    # HUD buddy: celebrate a win, mope after a loss (once per battle)
                    if self.pet is not None and request.get("battle_id") != getattr(self, "_pet_reacted", None):
                        self._pet_reacted = request.get("battle_id")
                        self.pet.react(request.get("result"))
                    self._game_ended_for_ball_hint(request.get("battle_id"))
                    _dbg(f"deck popup: battle {request.get('battle_id')} {request.get('deck')!r} "
                         f"({request.get('source')}, needs_input={request.get('needs_input')})")
            if self.deck_popup is not None:
                self.deck_popup.tick(menu_seen_at(), anchor, self.isVisible())
                self._position_chat_window()
            self._poll_concede(anchor)
        except Exception as exc:
            _dbg(f"_poll_deck_confirm error: {exc}")
        # The Reset? prompt is scheduled here, before the notice looks for it.
        self._poll_game_session()
        try:
            self._poll_decklist_card(anchor)
            self._poll_manual_mode_notice(anchor)
            self._poll_update(anchor)
        except Exception as exc:
            _dbg(f"_poll_deck_confirm error: {exc}")
        try:
            geo = self.frameGeometry()
            self._restack_limitless_cards((geo.right() + 1, geo.top() - 6))
            if self.hud_notifications():
                self._position_chat_window()
        except Exception as exc:
            _dbg(f"restack error: {exc}")
        self._poll_pet()
        self._poll_ball_hint()

    # The buddy hint: the mini GUI's ball rocks like a Pokeball with something
    # inside, rarely - after a game, 1 in 4 times, once, at a random moment
    # 10-120 s later, never once a new battle has started. Only while there's
    # something inside: the buddy not called out yet, or resting in the ball.
    BALL_HINT_ODDS = 0.25
    BALL_HINT_WINDOW_S = (10, 120)

    def _game_ended_for_ball_hint(self, battle_id):
        if battle_id == getattr(self, "_ball_hint_battle", None):
            return  # once per game
        self._ball_hint_battle = battle_id
        self._ball_hint_at = None
        if random.random() < self.BALL_HINT_ODDS:
            self._ball_hint_at = time.monotonic() + random.uniform(*self.BALL_HINT_WINDOW_S)
            self._ball_hint_after = time.time()  # a battle started after this cancels it

    def _ball_has_something_inside(self):
        if self.pet is not None:
            return self.pet.state == "ball"
        from pet import STATE_FILE  # anyone who ever had the buddy out has its save file
        return not (_overlay_setting("pet_discovered", False) or os.path.exists(STATE_FILE))

    def _poll_ball_hint(self):
        try:
            due = getattr(self, "_ball_hint_at", None)
            if due is None or getattr(self, "_ball_shaking", False) or time.monotonic() < due:
                return
            from deck_confirm import battle_started_at
            if battle_started_at() > getattr(self, "_ball_hint_after", 0.0):
                self._ball_hint_at = None  # in a battle again: not this time
                return
            if not self.isVisible():
                if time.monotonic() - due > 30:
                    self._ball_hint_at = None  # the mini GUI stayed hidden: not this time
                return
            self._ball_hint_at = None
            if self._ball_has_something_inside():
                self._shake_ball()
        except Exception as exc:
            _dbg(f"_poll_ball_hint error: {exc}")

    def _shake_ball(self):
        """One to three rocks, each smaller, with a pause between (the shakes
        of a ball in the games), tilting on the ball's bottom."""
        keys, t = [(0.0, 0.0)], 0.0
        for amp in (24.0, 17.0, 11.0)[:random.choice((1, 2, 2, 3))]:  # degrees; a 9 px sprite needs a real tip
            for angle in (-amp, 0.0, amp * 0.85, 0.0):
                t += 0.085
                keys.append((t, angle))
            t += random.uniform(0.25, 0.45)  # still for a moment
            keys.append((t, 0.0))
        self._ball_shaking, started = True, time.monotonic()
        timer = QTimer(self)
        timer.setInterval(16)

        def frame():
            age = time.monotonic() - started
            if age >= keys[-1][0]:
                timer.stop()
                timer.deleteLater()
                self._ball_shaking = False
                angle = 0.0
            else:
                i = next(n for n in range(1, len(keys)) if keys[n][0] > age)
                (t0, a0), (t1, a1) = keys[i - 1], keys[i]
                u = (age - t0) / max(1e-6, t1 - t0)
                angle = a0 + (a1 - a0) * (u * u * (3 - 2 * u))
            self._set_ball(angle)
        timer.timeout.connect(frame)
        timer.start()

    def _set_ball(self, angle=0.0):
        """The league's pixel-art ball, centred on the stats text's capitals."""
        pix = create_pokeball_icon(getattr(self, "_ball_league", "poke"), self.ball_icon.devicePixelRatioF(), angle, self._hud_scale)
        self.ball_icon.set_ball(pix, self.stats_label)

    def _on_clipboard_changed(self):
        try:
            from StatsUI import _list_or_link
            from decklists import already_have, is_ptcgl_decklist, save_decklist
            text = _list_or_link(QApplication.clipboard().text() or "")
            if not is_ptcgl_decklist(text):
                return
            if getattr(self.stats_window, "_decklist_dialog_open", False):
                return  # the "Link a decklist" window is taking it
            # Exported from the game (it has the focus): one of your decks, it
            # only needs saving. Copied anywhere else (a website, a chat): a
            # new deck, imported into the game and the app like a shared link.
            from_game = self._game_is_foreground()
            if already_have(text):
                # A list you already have (same cards, any order or prints):
                # never asked about again.
                if from_game:
                    save_decklist(text, self._menu_deck())   # just mark it as the newest
                _dbg("decklist on the clipboard: already in your decklists, not asked")
                return
            self._pending_decklist = text
            self._pending_from_game = from_game
            _dbg(f"decklist on the clipboard ({'from the game' if from_game else 'from elsewhere'}): "
                 f"asking whether to import it")
        except Exception as exc:
            _dbg(f"clipboard decklist check failed: {exc}")

    def _update_action(self, text):
        """The copied-list card's second button: "Update <deck>" for the deck
        whose list it's closest to, else "Update a deck…" (the dashboard's
        import panel, where you pick the deck)."""
        from decklists import closest_deck
        try:
            names = self.db.get_known_deck_names() if getattr(self, "db", None) is not None else []
        except Exception:
            names = []
        try:
            close = closest_deck(text, names)
        except Exception:
            close = None
        if close:
            deck = close[0]
            short = deck if len(deck) <= 16 else deck[:15].rstrip() + "…"
            return (f"Update {short}", lambda: self._update_deck_from_clipboard(deck, text))
        return ("Update a deck…", lambda: self._pick_deck_to_update(text))

    def _update_deck_from_clipboard(self, deck, text):
        from decklists import changes_text, update_deck_list
        import html as _html
        try:
            changes = update_deck_list(deck, text)
        except Exception as exc:
            _dbg(f"deck update failed: {exc}")
            return
        _dbg(f"decklist: {deck} updated ({len(changes)} changes)")
        if self.stats_window is not None:
            self.stats_window._deck_dashboards_dirty = True
        from deck_popup import NoticeCard
        card = NoticeCard("DECK UPDATED", f"<b>{_html.escape(deck)}</b><br>{changes_text(changes)}",
                          linger_ms=9000)
        self._decklist_card = card
        card.show_at(self._stack_anchor(self._hud_anchor(), "_decklist_card"))

    def _hud_anchor(self):
        geo = self.frameGeometry()
        return (geo.right() + 1, geo.top() - 6)

    def _pick_deck_to_update(self, text):
        """The dashboard's import panel with this list, ready to pick the deck."""
        self.open_stats_dashboard()
        window = self.stats_window
        if window is not None:
            QTimer.singleShot(0, lambda: window._import_decklist_dialog(None, preset_text=text))

    @staticmethod
    def _game_is_foreground():
        try:
            from game_window import find_game_hwnd
            hwnd = find_game_hwnd()
            return bool(hwnd) and win32gui.GetForegroundWindow() == hwnd
        except Exception:
            return False

    def _open_deck_import(self, text):
        """The shared-deck import box (deck_link.py): a name, then the deck
        goes into Pokémon TCG Live and onto the Decks tab."""
        import subprocess
        import deck_link
        import deck_share
        link = deck_share.share_url(text, web=False)
        proc = subprocess.Popen([deck_link._gui_python(), os.path.join(BASE_DIR, "deck_link.py"),
                                 link, "--from-clipboard"], cwd=BASE_DIR)
        _dbg(f"decklist import box opened (pid {proc.pid})")
        timer = QTimer(self)
        timer.setInterval(1000)

        def check():
            if proc.poll() is None:
                return
            timer.stop()
            timer.deleteLater()
            window = self.stats_window
            if window is None:
                return
            window._deck_dashboards_dirty = True
            try:
                if window.isVisible():
                    window._refresh_deck_dashboards()
            except Exception as exc:
                _dbg(f"deck tabs refresh after the import failed: {exc}")
        timer.timeout.connect(check)
        timer.start()
        return proc

    @staticmethod
    def _menu_deck():
        try:
            with open(os.path.join(BASE_DIR, ".last_deck"), "r", encoding="utf-8") as handle:
                return handle.read().strip() or None
        except OSError:
            return None

    def _poll_decklist_card(self, anchor):
        """Ask about a copied decklist: Import (stored like a PTCGL export,
        ready for the Decks tab and Print your decklist) or Not now."""
        card = getattr(self, "_decklist_card", None)
        try:
            if card is not None and card.isVisible():
                card.reposition(self._stack_anchor(anchor, "_decklist_card"))
                return
        except RuntimeError:
            self._decklist_card = None
        if not self._pending_decklist or not self.isVisible():
            return  # (kept until the HUD is showing)
        text, self._pending_decklist = self._pending_decklist, None
        from deck_popup import NoticeCard
        from decklists import auto_name
        import html as _html

        # Or a new version of one of your decks: Update it (the closest one by
        # its cards), or pick which on the dashboard.
        update = self._update_action(text)
        if not getattr(self, "_pending_from_game", True):
            self._decklist_card = NoticeCard(
                "DECKLIST COPIED",
                f"<b>{_html.escape(auto_name(text))}</b>. Import it into Pokémon TCG Live and your decks, "
                f"or update one of your decks with it?",
                primary=("Import", lambda: self._open_deck_import(text)), secondary=update,
                linger_ms=30000)
            self._decklist_card.show_at(self._stack_anchor(anchor, "_decklist_card"))
            return

        def do_import():
            from decklists import save_decklist
            entry = save_decklist(text, self._menu_deck())
            _dbg(f"decklist imported: {entry['deck']} ({entry['cards']} cards)")
            if self.stats_window is not None:
                self.stats_window._deck_dashboards_dirty = True

        self._decklist_card = NoticeCard(
            "DECKLIST COPIED",
            f"<b>{_html.escape(auto_name(text))}</b>. Import it into your decklists, or update a deck's list?",
            primary=("Import", do_import), secondary=update, linger_ms=30000)
        self._decklist_card.show_at(self._stack_anchor(anchor, "_decklist_card"))

    def _poll_concede(self, anchor):
        """A battle went straight to the main menu (deck_confirm.ask_concede):
        ask whether it was a concede. Yes adds the loss, and the deck card
        then asks for the opponent's deck like after any battle."""
        card = getattr(self, "_concede_card", None)
        try:
            if card is not None and card.isVisible():
                card.reposition(self._stack_anchor(anchor, "_concede_card"))
                return
        except RuntimeError:  # closed
            self._concede_card = None
        from deck_confirm import (CONCEDE_FILE, concede_text, mark_concede_handled,
                                  read_concede)
        try:
            mtime = os.path.getmtime(CONCEDE_FILE)
        except OSError:
            return
        if mtime == getattr(self, "_concede_mtime", None):
            return
        self._concede_mtime = mtime
        question = read_concede()
        if not question:
            return
        mark_concede_handled()  # asked once, even if the card is closed with X

        def conceded():
            from deck_confirm import record_concede, write_request
            battle_id = record_concede(self.db, question)
            _dbg(f"concede: added loss as battle {battle_id}")
            if battle_id:
                write_request(battle_id, "", source="none", needs_input=True,
                              my_deck=question.get("my_deck"), result="Loss")

        from deck_popup import NoticeCard
        self._concede_card = NoticeCard("DID YOU CONCEDE?", concede_text(question),
                                        primary=("Yes, add a loss", conceded),
                                        secondary=("No", lambda: None), linger_ms=0)
        self._concede_card.show_at(self._stack_anchor(anchor, "_concede_card"))
        _dbg("concede question shown")

    def _poll_manual_mode_notice(self, anchor):
        """Once per launch, when the mini GUI is placed: no OpenAI key (or
        local-only mode) means opponent decks are asked for by hand - say so,
        and offer the key setting. Stacks above the deck card if both show."""
        notice = getattr(self, "_manual_notice", None)
        if notice is not None:
            if notice.isVisible():
                notice.reposition(self._stack_anchor(anchor, "_manual_notice"))
            return
        if getattr(self, "_manual_notice_checked", False) or not self.isVisible():
            return
        # One card at a time: wait for the Reset? prompt (pending or showing)
        # to finish, then a short pause.
        reset = getattr(self, "_reset_popup", None)
        try:
            reset_showing = reset is not None and reset.isVisible()
        except RuntimeError:
            reset_showing = False
        if reset_showing or getattr(self, "_session_prompt_due", None) is not None:
            self._notice_hold_until = time.time() + 2.0
            return
        if time.time() < getattr(self, "_notice_hold_until", 0.0):
            return
        self._manual_notice_checked = True
        try:
            import ai_provider
            from app_settings import is_local_only_mode
            local_only = is_local_only_mode()
            has_key = ai_provider.ai_ready()
            provider = ai_provider.configured_provider()
        except Exception as exc:
            _dbg(f"manual notice check failed: {exc}")
            return
        if has_key and not local_only:
            return
        if not _overlay_setting("manual_mode_notice", True):
            return
        from deck_popup import NoticeCard
        # What manual mode means: no AI, only the opponent's revealed cards.
        how = ("The opponent's deck is guessed only from the cards they played, which is less "
               "accurate than AI. After each battle, check the guess or pick the deck yourself.")
        if local_only:
            title, text = "LOCAL MODE", how
            primary = ("Open Settings", self.open_api_key_setting)
        elif provider in ("hosted", "compatible"):
            title, text = "MANUAL MODE", ("AI unavailable"
                                          + (" (built-in AI unreachable). " if provider == "hosted"
                                             else ": set a base URL and model. ") + how)
            primary = ("Open Settings", self.open_api_key_setting)
        else:
            title, text = "MANUAL MODE", "No AI is set up. " + how
            primary = ("Add API key", self.open_api_key_setting)
        self._manual_notice = NoticeCard(title, text, primary=primary,
                                         secondary=("Don't remind me", self._mute_manual_notice))
        self._manual_notice.show_at(self._stack_anchor(anchor, "_manual_notice"))
        _dbg(f"manual mode notice shown (local_only={local_only}, has_key={has_key})")

    # Cards over the mini GUI, bottom to top. Each sits above the visible
    # cards before it, and the chat above them all, so a deck card, a
    # report or friend question and the chat never cover each other.
    HUD_CARD_ORDER = ("deck_popup", "_reset_popup", "_concede_card", "_decklist_card", "_manual_notice", "_update_card")

    def _hud_card_stack(self):
        stack = [(name, getattr(self, name, None)) for name in self.HUD_CARD_ORDER]
        manager = getattr(self, "limitless_manager", None)
        for card in (getattr(manager, "hud_notifications", lambda: [])() if manager else []):
            stack.append((card, card))
        return stack

    def _stack_anchor(self, anchor, target):
        """anchor (right, bottom) moved above every visible card that comes
        before `target` (a name from HUD_CARD_ORDER, or the card itself)."""
        top = anchor[1]
        for key, card in self._hud_card_stack():
            if key == target or (card is not None and card is target):
                break
            try:
                if card is not None and card.isVisible():
                    top = min(top, card.y() - 6)
            except RuntimeError:  # deleted
                pass
        return (anchor[0], top)

    def _restack_limitless_cards(self, anchor):
        manager = getattr(self, "limitless_manager", None)
        for card in (getattr(manager, "hud_notifications", lambda: [])() if manager else []):
            try:
                if card is not None and card.isVisible():
                    right, bottom = self._stack_anchor(anchor, card)
                    card.move(int(right - card.width()), int(bottom - card.height()))
            except RuntimeError:
                pass

    UPDATE_CHECK_DELAY_S = 25  # after the mini GUI is placed: let the game settle first

    def _poll_update(self, anchor):
        """Once per launch: look for a newer release (updater.py) on a worker
        thread; offer it in a card above the mini GUI."""
        card = getattr(self, "_update_card", None)
        if card is not None and card.isVisible():
            card.reposition(self._stack_anchor(anchor, "_update_card"))
        state = getattr(self, "_update_state", None)
        if state is None:
            self._update_state = state = {"placed_at": time.time(), "result": None, "checking": False,
                                          "done": False, "manual": False, "download": None}
        if state["done"] or not self.isVisible():
            return
        if not state["checking"] and state["result"] is None:
            if not state["manual"]:
                if not _overlay_setting("check_updates", True):
                    state["done"] = True
                    return
                if time.time() - state["placed_at"] < self.UPDATE_CHECK_DELAY_S:
                    return
            state["checking"] = True

            def work():
                try:
                    import updater
                    from app_settings import load_app_settings
                    settings = {} if state["manual"] else load_app_settings()
                    release = updater.update_available(settings)
                    state["result"] = ("update", release) if release else ("none", None)
                except Exception as exc:
                    state["result"] = ("error", str(exc))
                state["checking"] = False
            threading.Thread(target=work, daemon=True).start()
            return
        if state["checking"] or state["result"] is None:
            return
        state["done"] = True
        kind, release = state["result"]
        _dbg(f"update check: {kind} {release.get('version') if isinstance(release, dict) else release}")
        if kind == "update":
            self._show_update_card(release, anchor)
        elif state["manual"]:
            self._show_update_card(None, anchor)

    def check_for_updates(self):
        """Settings → "Check now": check immediately (skipped version included)."""
        self._update_state = {"placed_at": 0, "result": None, "checking": False, "done": False,
                              "manual": True, "download": None}
        old = getattr(self, "_update_card", None)
        if old is not None:
            old.close()
            self._update_card = None

    def _show_update_card(self, release, anchor):
        from deck_popup import UpdateCard
        import updater
        from version import APP_VERSION
        card = UpdateCard(APP_VERSION, release, updater.can_self_install())
        self._update_card = card
        if release is None:
            card.show_up_to_date(APP_VERSION)
        card.on_later = card.close
        card.on_page = lambda: (webbrowser.open((release or {}).get("page") or updater.RELEASES_PAGE))

        def skip():
            from app_settings import load_app_settings, save_app_settings
            settings = load_app_settings()
            settings["skip_update_version"] = release.get("version")
            save_app_settings(settings)
            card.close()
        card.on_skip = skip
        card.on_update = lambda: self._start_update(card, release)
        card.show_at(self._stack_anchor(anchor, "_update_card"))

    def _start_update(self, card, release):
        """Download (worker thread), verify, run the installer silently, quit.
        The installer stops the monitor too and starts it again afterwards."""
        import updater
        job = {"done": 0, "total": 0, "path": None, "error": None, "finished": False}

        def work():
            try:
                job["path"] = updater.download(
                    release, progress=lambda d, t: job.update(done=d, total=t))
            except Exception as exc:
                job["error"] = str(exc) or type(exc).__name__
            job["finished"] = True
        threading.Thread(target=work, daemon=True).start()
        card.show_progress(0, (release.get("installer") or {}).get("size") or 0)
        timer = QTimer(card)
        timer.setInterval(200)

        def tick():
            if not job["finished"]:
                card.show_progress(job["done"], job["total"])
                return
            timer.stop()
            if job["error"]:
                _dbg(f"update download failed: {job['error']}")
                card.show_error(f"Couldn't download the update ({job['error']}).")
                return
            card.show_installing()
            try:
                updater.launch_installer(job["path"])
            except Exception as exc:
                _dbg(f"update launch failed: {exc}")
                card.show_error(f"Couldn't start the installer ({exc}).")
                return
            _dbg(f"update installer started: {job['path']}")
            QTimer.singleShot(2500, QApplication.quit)  # the installer closes the rest
        timer.timeout.connect(tick)
        timer.start()

    def _mute_manual_notice(self):
        try:
            from app_settings import load_app_settings, save_app_settings
            settings = load_app_settings()
            settings["manual_mode_notice"] = False
            save_app_settings(settings)
        except Exception as exc:
            _dbg(f"mute manual notice failed: {exc}")

    def _poll_minimize_request(self):
        """A shared-deck import (ptcgl_import) is about to drive the game:
        tuck the always-on-top dashboard away so it can't cover the clicks."""
        try:
            import ptcgl_import
            if not ptcgl_import.take_minimize_request():
                return
            window = self.stats_window
            if window is not None and window.isVisible():
                window.minimize_to_overlay()
        except Exception as exc:
            _dbg(f"minimize request failed: {exc}")

    def _reopen_dashboard(self, tab=None):
        try:
            self.animate_arrow("▼")
            self.open_stats_dashboard()
            window = self.stats_window
            if window is not None and tab:
                index = window._main_tab_index(tab)
                if index >= 0:
                    window.tab_widget.setCurrentIndex(index)
        except Exception as exc:
            _dbg(f"reopen dashboard failed: {exc}")

    def restart_ui(self, tab=None):
        """Quit; the monitor relaunches the overlay at once (ui_restart)."""
        import ui_restart
        ui_restart.request(tab)
        _dbg(f"restart requested (tab={tab})")
        self._restarting = True
        # exit(), not quit(): Qt 6's quit() asks every window to close first and
        # gives up when one refuses (the hosted dashboard hides instead).
        QApplication.instance().exit(0)

    def open_api_key_setting(self):
        """Dashboard -> Settings, at the OpenAI key field."""
        try:
            if self.stats_window is None or not self.stats_window.isVisible():
                self.animate_arrow("▼")
                self.open_stats_dashboard()
            if self.stats_window is not None:
                self.stats_window.show_api_key_setting()
        except Exception as exc:
            _dbg(f"open_api_key_setting failed: {exc}")

    def _on_ball_double_click(self):
        """The mini GUI's Pokeball: the first double-click calls the HUD buddy
        out (turns it on); after that it recalls / sends it out."""
        if getattr(self, "pet", None) is None:
            try:
                from app_settings import load_app_settings, save_app_settings
                settings = load_app_settings()
                settings["overlay_pet"] = True
                settings["pet_discovered"] = True  # the ball stops hinting
                save_app_settings(settings)
            except Exception as exc:
                _dbg(f"pet enable failed: {exc}")
                return
            self._pet_summoned = True
            self._poll_pet()
            if self.pet is not None:
                QTimer.singleShot(200, self.pet.toggle_ball)
            return
        self.pet.toggle_ball()

    def _game_floor_drop(self):
        """Logical px from the mini GUI's bottom down to the game's visible
        bottom edge (its client area: GetWindowRect also counts Windows'
        invisible resize border, ~10 px)."""
        dpr = self.devicePixelRatioF() or 1.0
        try:
            hwnd = getattr(self, "game_hwnd", None)
            _l, _t, cw, ch = win32gui.GetClientRect(hwnd)
            client_bottom = win32gui.ClientToScreen(hwnd, (cw, ch))[1]
            mini_bottom = getattr(self, "_last_pos", (0, 0))[1] + int(self.height() * dpr)
            return max(0.0, (client_bottom - mini_bottom) / dpr)
        except Exception:
            return 2.0

    def _poll_pet(self):
        """HUD buddy: create / drop / re-species it as the setting changes,
        keep it beside the mini GUI and hidden whenever the overlay is."""
        try:
            wanted = bool(_overlay_setting("overlay_pet", False))
            if not wanted:
                if self.pet is not None:
                    self.pet.close()
                    self.pet.deleteLater()
                    self.pet = None
                return
            species = _overlay_setting("overlay_pet_species", "pikachu")
            from deck_confirm import battle_started_at, menu_seen_at
            started = battle_started_at()
            if self.pet is None:
                from pet import PetWidget
                self.pet = PetWidget(species, in_ball=getattr(self, "_pet_summoned", False))
                self._pet_summoned = False
                self._pet_battle_seen = started  # don't react to a battle from before
                self._pet_menu_seen = menu_seen_at()
            else:
                self.pet.set_species(species)
            if started > getattr(self, "_pet_battle_seen", 0.0):
                self._pet_battle_seen = started
                if time.time() - started < 60:
                    self.pet.battle_start()
            menu = menu_seen_at()
            if menu > getattr(self, "_pet_menu_seen", 0.0):
                self._pet_menu_seen = menu
                self.pet.menu_seen()
            show = self.isVisible() and getattr(self, "_overlay_placed", False)
            if show:
                self.pet.follow(self.frameGeometry(), self.ball_icon.mapToGlobal(self.ball_icon.rect().center()),
                                drop=self._game_floor_drop())
                if not self.pet.isVisible():
                    self.pet.show()
            elif self.pet.isVisible():
                self.pet.hide()
        except Exception as exc:
            _dbg(f"_poll_pet error: {exc}")

    def _poll_game_session(self):
        """New Pokemon TCG Live session (monitor wrote .game_session): offer
        today's W-L reset in a popup that fades by itself."""
        try:
            with open(GAME_SESSION_FILE, "r", encoding="utf-8") as handle:
                started = float(handle.read().strip() or 0)
        except (OSError, ValueError):
            return
        if started != self._session_seen:
            self._session_seen = started
            self._session_prompt_due = started
        due = self._session_prompt_due
        if due is None:
            return
        if time.time() - due > SESSION_PROMPT_WINDOW_S:
            self._session_prompt_due = None
            return
        if not self.isVisible() or not getattr(self, "_overlay_placed", False):
            return  # wait until the mini GUI sits on the game window
        self._session_prompt_due = None
        if not _overlay_setting("overlay_session_reset_prompt", True):
            return
        if self.wins + self.losses <= 0:
            return  # nothing to reset
        if getattr(self, "_reset_popup", None) is not None and self._reset_popup.isVisible():
            return
        _dbg(f"session reset prompt ({self.wins}-{self.losses})")
        self.confirm_reset_today_stats(linger_ms=SESSION_PROMPT_LINGER_MS)

    def check_monitor_running(self):
        """Check if TCGLiveMonitor.py is still running via PID file"""
        try:
            pid_file = os.path.join(BASE_DIR, '.monitor_pid')
            monitor_running = False
            if os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    content = f.read().strip()
                pid = int(content.split()[0]) if content else 0
                monitor_running = self._is_monitor_pid(pid) if pid else False

            if not monitor_running and self.parent_monitor_running:
                _dbg("Monitor PID gone - quitting overlay")
                print("Monitor closed, shutting down overlay...")
                QApplication.quit()

            self.parent_monitor_running = monitor_running
        except Exception:
            pass  # never block the event loop

    @staticmethod
    def _is_monitor_pid(pid):
        """True only if pid is alive AND is our monitor (PIDs get recycled)."""
        try:
            proc = psutil.Process(pid)
            cmd = " ".join(proc.cmdline() or [])
            return proc.is_running() and ("TCGLiveMonitor" in cmd)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return False
        except psutil.AccessDenied:
            return True  # alive but not inspectable; assume ours
        except Exception:
            return psutil.pid_exists(pid)

    @staticmethod
    def _is_game_title(title):
        normalized = (title or "").strip().lower()
        return normalized in {"pokemon tcg live", "pokémon tcg live"}

    def _is_monitor_owned_window(self, hwnd):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid or pid == os.getpid():
                return True

            process = psutil.Process(pid)
            cmdline = " ".join(process.cmdline()).lower()
            return any(
                marker in cmdline
                for marker in (
                    "tcglivemonitor.py",
                    "overlayui.py",
                    "statsui.py",
                    "setupstartup.py",
                    "run_headless.py",
                    "autorun_add.py",
                    "autorun_remove.py",
                )
            )
        except Exception:
            return False

    def _is_valid_game_window(self, hwnd):
        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return False

            if win32gui.GetClassName(hwnd) == "ConsoleWindowClass":
                return False

            title = win32gui.GetWindowText(hwnd)
            if not self._is_game_title(title):
                return False

            if self._is_monitor_owned_window(hwnd):
                return False

            return True
        except Exception:
            return False
    
    def _game_hidden_windows(self):
        return [w for w in (getattr(self, "chat_window", None), getattr(self, "deck_icon", None),
                            getattr(self, "deck_popup", None)) if w is not None]

    def _hide_with_game(self):
        """Hide the mini HUD and its satellites while the game is minimized;
        _show_with_game brings back the ones that were up."""
        if getattr(self, "_hidden_for_game", None) is None:
            self._hidden_for_game = [w for w in self._game_hidden_windows() if w.isVisible()]
            _dbg("game minimized: HUD hidden")
        chat = getattr(self, "chat_window", None)
        if chat is not None:
            chat.suppressed = True
        for w in self._game_hidden_windows():
            if w.isVisible():
                w.hide()
        if self.isVisible():
            self.hide()

    def _show_with_game(self):
        hidden = getattr(self, "_hidden_for_game", None)
        if hidden is None:
            return
        self._hidden_for_game = None
        chat = getattr(self, "chat_window", None)
        if chat is not None:
            chat.suppressed = False
        if not self.isVisible():
            self.show()
        for w in hidden:
            if w is getattr(self, "deck_icon", None):  # the icon follows the chat by itself
                continue
            if w is chat and chat.retired:
                continue
            w.show()
        _dbg("game restored: HUD shown")

    def find_game_window(self):
        """Find Pokemon TCG Live window, cached to avoid EnumWindows every tick"""
        # Fast path: verify cached hwnd is still the game window
        if self.game_hwnd and self._is_valid_game_window(self.game_hwnd):
            return self.game_hwnd

        # Slow path: enumerate all windows only when cache is stale
        def callback(hwnd, hwnds):
            if self._is_valid_game_window(hwnd):
                hwnds.append(hwnd)
            return True

        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        result = hwnds[0] if hwnds else None
        if result:
            _dbg(f"find_game_window: re-acquired hwnd={result}")
        return result
    
    def follow_game_window(self):
        """Position overlay flush to bottom-right corner of game window"""
        hwnd = self.find_game_window()
        if not hwnd:
            if self.isVisible():
                self.hide()
                _dbg("follow_game_window: game not found, hidden")
            return

        self.game_hwnd = hwnd

        try:
            # GetWindowRect returns physical pixels (DPI-aware process).
            # self.width()/height() are logical pixels. Multiply by DPR to get
            # physical dimensions so both values are in the same unit.
            game_left, game_top, game_right, game_bottom = win32gui.GetWindowRect(hwnd)
            # Minimized, or parked at Windows' minimized spot (-32000) without
            # being flagged iconic (the game sometimes ends up there): the HUD
            # and everything on it go with it.
            if win32gui.IsIconic(hwnd) or game_left <= -30000 or game_top <= -30000:
                self._hide_with_game()
                return
            self._show_with_game()

            # Sanity check — skip if window is in an invalid state
            if game_right <= 0 or game_bottom <= 0:
                return

            dpr = self.devicePixelRatioF() or 1.0
            phys_w = int(self.width() * dpr)
            phys_h = int(self.height() * dpr)
            # Inset the mini UI a few pixels inside the visible window edge so
            # it doesn't sit flush against (or clip) the corner.
            margin = 12  # physical pixels inside the visible window edge

            x = game_right - phys_w - margin
            y = game_bottom - phys_h - margin

            if (x, y) != getattr(self, "_last_pos", None):
                _dbg(f"pos: game=({game_right},{game_bottom}) dpr={dpr} phys={phys_w}x{phys_h} -> ({x},{y})")
                self._last_pos = (x, y)

            if not self.isVisible():
                self.show()

            # Keep the standalone chat window glued above the mini GUI.
            self._position_chat_window()

            overlay_hwnd = int(self.winId())
            # If stats dashboard is open, leave z-order alone while the popup is in use.
            if self.stats_window and self.stats_window.isVisible():
                return
            else:
                win32gui.SetWindowPos(
                    overlay_hwnd,
                    win32con.HWND_TOPMOST,
                    x, y, 0, 0,
                    win32con.SWP_NOACTIVATE | win32con.SWP_NOSIZE
                )
                # Popups anchored to the mini GUI may only be placed from now on.
                self._overlay_placed = True
                if not getattr(self, "_tutorial_checked", False):
                    self._tutorial_checked = True  # once per run; not after a restart
                    if not getattr(self, "_restart_note", None):
                        QTimer.singleShot(2500, self._maybe_start_tutorial)
                if getattr(self, "_restart_note", None):
                    note, self._restart_note = self._restart_note, None
                    QTimer.singleShot(300, lambda: self._reopen_dashboard(note.get("tab")))
                self._position_reset_popup()
        except Exception as e:
            _dbg(f"follow_game_window exception: {e}")
    
    def init_ui(self):
        """Initialize minimal UI"""
        # Window properties - clickable but stays on top
        self.setWindowTitle("TCG Monitor")
        from app_settings import get_scale
        self._hud_scale = get_scale("hud_scale")  # Settings -> HUD size; read at start
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        # Container
        self.container = QFrame()
        self.container.setObjectName("container")
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)
        
        # Container layout
        layout = QVBoxLayout(self.container)
        k = self._hud_scale
        layout.setContentsMargins(round(6 * k), round(4 * k), round(6 * k), round(4 * k))
        layout.setSpacing(round(2 * k))

        # The Limitless match chat lives in its own standalone window
        # (LimitlessChatWindow) positioned ABOVE this mini GUI — it is fully
        # transparent, click-through, and fades with height and time.
        self.chat_window = None

        # Stats display with pokeball icon
        stats_layout = QHBoxLayout()
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(round(4 * k))
        
        # Pokeball icon label
        self.ball_icon = PixelBall()
        self.ball_icon.setFixedSize(round(12 * k), round(12 * k))
        # Double-click the ball: recall / send out the HUD buddy (pet.py)
        self.ball_icon.mouseDoubleClickEvent = lambda e: self._on_ball_double_click()
        stats_layout.addWidget(self.ball_icon)
        
        # Stats text label — double-click opens a mini reset popup
        self.stats_label = QLabel("Elo:-- | Max:-- | 0-0")
        self.stats_label.setObjectName("stats")
        self.stats_label.setToolTip("Double-click to reset today")
        self.stats_label.mouseDoubleClickEvent = lambda e: self.confirm_reset_today_stats()
        stats_layout.addWidget(self.stats_label)
        
        # Small arrow indicator (clickable)
        self.arrow_label = QLabel("▲")
        self.arrow_label.setObjectName("arrow")
        self.arrow_label.setFixedSize(round(10 * k), round(12 * k))
        self.arrow_label.mousePressEvent = lambda e: self.toggle_stats_dashboard()
        stats_layout.addWidget(self.arrow_label)
        
        layout.addLayout(stats_layout)
        
        # Apply minimal styling
        self.apply_style()
        
        # Let the widget size itself to fit content
        self.adjustSize()
    
    def apply_style(self):
        """Apply minimal, professional styling"""
        k = self._hud_scale
        self.setStyleSheet("""
            QWidget {
                background-color: #141414;
            }
            QFrame#container {
                background-color: #141414;
                border: 1px solid #505050;
                border-radius: 4px;
            }
            QLabel#stats {
                color: #DCDCDC;
                font-family: 'Segoe UI', Arial;
                font-size: %dpx;
                font-weight: 500;
                background-color: transparent;
            }
            QLabel#arrow {
                color: #C8C8C8;
                font-family: 'Segoe UI', Arial;
                font-size: %dpx;
                background-color: transparent;
            }
            QLabel#arrow:hover {
                color: #FFFFFF;
            }
        """ % (round(11 * k), round(9 * k)))
    
    def load_stats(self):
        """Load stats from database and files"""
        try:
            # Try database first for current rank
            db_rank = self.db.get_current_rank()
            if db_rank:
                self.current_rank = str(db_rank)
            else:
                # Fallback to file
                rank_file = os.path.join(BASE_DIR, '.last_rank')
                if os.path.exists(rank_file):
                    with open(rank_file, 'r') as f:
                        self.current_rank = f.read().strip()
            
            # Try database for max rank
            db_max_rank = self.db.get_max_rank()
            if db_max_rank:
                self.max_rank = str(db_max_rank)
            else:
                # Fallback to file
                max_rank_file = os.path.join(BASE_DIR, '.max_rank')
                if os.path.exists(max_rank_file):
                    with open(max_rank_file, 'r') as f:
                        self.max_rank = f.read().strip()
            
            # Get W/L from database (much faster!)
            self.wins, self.losses = self.db.get_today_stats(ignored_decks())
            
            # Update display
            self.update_display()

        except Exception as e:
            _dbg(f"load_stats error: {e}")

    def _make_pokeball_icon(self, size=12, color="#FFD9D9"):
        """Draw a tiny subtle pokeball glyph for the Reset button.

        Simple flat pokeball: top half filled with the accent color, bottom
        half transparent-ish, center band + button dot. Kept faint so it
        reads as an accent, not a mascot.
        """
        dpr = max(1.0, self.devicePixelRatioF())  # drawn at screen resolution, not stretched
        pixmap = QPixmap(int(round(size * dpr)), int(round(size * dpr)))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Outline circle
        pen = QColor(color)
        pen.setAlpha(220)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(1, 1, size - 2, size - 2)
        # Top half fill (faint)
        fill = QColor(color)
        fill.setAlpha(70)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPie(1, 1, size - 2, size - 2, 0 * 16, 180 * 16)
        # Center band
        band = QColor(color)
        band.setAlpha(200)
        p.setBrush(band)
        p.drawRect(1, size / 2.0 - 0.75, size - 2, 1.5)
        # Center dot
        p.setBrush(QColor(color))
        p.drawEllipse(size / 2.0 - 1.75, size / 2.0 - 1.75, 3.5, 3.5)
        p.end()
        return QPixmap(pixmap)

    def confirm_reset_today_stats(self, linger_ms=None):
        """Tiny frameless popup matching the overlay style: "Reset?" + red Reset.
        linger_ms: the new-session version, which fades out by itself."""
        try:
            # Reuse the existing popup if it's already open.
            if getattr(self, "_reset_popup", None) is not None and self._reset_popup.isVisible():
                self._reset_popup.close()
                return

            # A touch of transparency for the whole popup.
            popup = FadingPopup(linger_ms=linger_ms, opacity=0.92)
            popup.setObjectName("resetPopup")

            card = QFrame()
            card.setObjectName("resetCard")
            v = QVBoxLayout(card)
            v.setContentsMargins(9, 6, 9, 7)
            v.setSpacing(4)

            if linger_ms:
                session = QLabel("New session")
                session.setObjectName("resetSession")
                session.setAlignment(Qt.AlignmentFlag.AlignCenter)
                v.addWidget(session)
            current = QLabel(f"Reset?  ({self.wins}-{self.losses})")
            current.setObjectName("resetCurrent")
            current.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(current)

            row = QHBoxLayout()
            row.setSpacing(4)

            reset_btn = QPushButton(" Reset")
            reset_btn.setObjectName("resetConfirmBtn")
            reset_btn.setIcon(self._make_pokeball_icon(12))
            reset_btn.setIconSize(QSize(12, 12))
            reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            reset_btn.setFixedHeight(18)
            reset_btn.clicked.connect(
                lambda: self._do_reset_today(popup)
            )
            row.addWidget(reset_btn)

            cancel_btn = QPushButton("✕")
            cancel_btn.setObjectName("resetCancelBtn")
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.setFixedSize(18, 18)
            cancel_btn.setToolTip("Cancel")
            cancel_btn.clicked.connect(popup.close)
            row.addWidget(cancel_btn)

            v.addLayout(row)

            outer = QVBoxLayout(popup)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(card)

            popup.setStyleSheet(self._reset_popup_style())
            self._reset_popup = popup

            popup.adjustSize()
            self._position_reset_popup()
            popup.show_animated()
            _dbg("Reset popup opened")
        except Exception as e:
            _dbg(f"confirm_reset_today_stats error: {e}")

    def _position_reset_popup(self):
        """Keep the Reset? popup just above the mini GUI (and the deck card,
        if showing), right-aligned with it. Re-run whenever the overlay moves."""
        popup = getattr(self, "_reset_popup", None)
        if popup is None:
            return
        try:
            geo = self.frameGeometry()
            top = geo.top()
            deck_card = getattr(self, "deck_popup", None)
            if deck_card is not None and deck_card.isVisible():
                top = min(top, deck_card.geometry().y())
            popup.move(geo.right() - popup.width(), top - popup.height() - 6)
        except RuntimeError:  # popup already deleted
            self._reset_popup = None

    def _do_reset_today(self, popup):
        try:
            self.db.reset_today_stats()
            self.wins, self.losses = 0, 0
            self.update_display()
            _dbg("Session stats reset via overlay popup")
        except Exception as e:
            _dbg(f"reset error: {e}")
        finally:
            popup.close()

    def _reset_popup_style(self):
        return """
            QFrame#resetCard {
                background-color: rgba(20, 20, 20, 0.88);
                border: 1px solid rgba(80, 80, 80, 0.85);
                border-radius: 10px;
            }
            QLabel#resetSession {
                color: #8E959E;
                font-family: 'Segoe UI', Arial;
                font-size: 8px;
                font-weight: 700;
                letter-spacing: 0.5px;
                background-color: transparent;
            }
            QLabel#resetCurrent {
                color: #DCDCDC;
                font-family: 'Segoe UI', Arial;
                font-size: 9px;
                font-weight: 500;
                background-color: transparent;
            }
            QPushButton#resetConfirmBtn {
                background-color: rgba(139, 26, 26, 0.85);
                border: 1px solid rgba(178, 34, 34, 0.9);
                border-radius: 9px;
                color: #FFECEC;
                font-family: 'Segoe UI', Arial;
                font-size: 9px;
                font-weight: 700;
                padding: 1px 9px;
            }
            QPushButton#resetConfirmBtn:hover {
                background-color: rgba(178, 34, 34, 0.95);
                border-color: #D33A3A;
                color: #FFFFFF;
            }
            QPushButton#resetConfirmBtn:pressed {
                background-color: rgba(110, 20, 20, 0.95);
            }
            QPushButton#resetCancelBtn {
                background-color: transparent;
                border: 1px solid rgba(80, 80, 80, 0.8);
                border-radius: 9px;
                color: #9A9A9A;
                font-size: 8px;
                font-weight: 700;
            }
            QPushButton#resetCancelBtn:hover {
                border-color: #808080;
                color: #DCDCDC;
            }
        """

    def update_limitless_chat(self, payload):
        try:
            state = payload if isinstance(payload, dict) else {}
            # Messages are dicts: {text, type, sender, ts}. Normalize legacy strings.
            messages = []
            for msg in (state.get("messages") or []):
                if isinstance(msg, dict):
                    text = str(msg.get("text") or "").strip()
                    mtype = str(msg.get("type") or "chat")
                    sender = str(msg.get("sender") or "").strip()
                    ts = msg.get("ts") or ""
                else:
                    text = str(msg).strip()
                    mtype = "chat"
                    sender = ""
                    ts = ""
                if text:
                    messages.append({"text": text, "type": mtype, "sender": sender, "ts": ts,
                                     "own": bool(isinstance(msg, dict) and msg.get("own"))})
            if not messages and not state.get("active"):
                self.limitless_chat_state = {}
                if self.chat_window is not None:
                    self.chat_window.hide()
                return

            self.limitless_chat_state = state
            # Lazily create the chat card and keep it above this mini GUI.
            if self.chat_window is None:
                self.chat_window = LimitlessChatWindow()
                self.chat_window.on_resized = self._position_chat_window
                self.chat_window.on_send = self._send_limitless_chat
                self.deck_icon = DeckIconWindow(self.chat_window, self._opponent_deck_ready,
                                                self._open_opponent_deck)
            # The player's username right-aligns their own messages.
            try:
                from app_settings import load_username
                own_name = load_username() or ""
            except Exception:
                own_name = ""
            opponent = str(state.get("opponent") or "").strip()
            title = " · ".join(t for t in (state.get("subtitle") or "",
                                            f"vs {opponent}" if opponent else "") if t)
            is_new = self.chat_window.set_messages(messages, own_name=own_name,
                                                   title=title or "Limitless chat",
                                                   opponent=opponent)
            self._retire_chat_later(state, messages, is_new)
            self._position_chat_window()
            if is_new and messages and not self.chat_window.suppressed and not self.chat_window._is_own(messages[-1]):
                self._ping_new_chat()
        except Exception as exc:
            _dbg(f"update_limitless_chat error: {exc}")

    CHAT_RETIRE_MS = 3 * 60 * 1000

    def _retire_chat_later(self, state, messages, is_new):
        """Once the round is reported (or the match page says it finished),
        the chat and its deck icon go away after CHAT_RETIRE_MS. A new message
        or the next round's page brings them back."""
        chat = self.chat_window
        url = state.get("url") or ""
        if not state.get("match_done") or is_new or url != getattr(self, "_retire_url", url):
            if chat.retired:
                chat.retired = False
                _dbg("chat back: new message or new match")
                if not chat.suppressed and not chat.isVisible():
                    chat.show()
            self._retire_token = getattr(self, "_retire_token", 0) + 1
            self._retire_url = url
            if not state.get("match_done"):
                return
        if chat.retired or getattr(self, "_retire_pending", None) == (url, self._retire_token):
            return
        self._retire_url = url
        token = self._retire_token
        self._retire_pending = (url, token)

        def retire():
            self._retire_pending = None
            if token != getattr(self, "_retire_token", 0) or self.chat_window is not chat:
                return
            chat.retired = True
            chat.hide()
            icon = getattr(self, "deck_icon", None)
            if icon is not None:
                icon.hide()
            _dbg("round over: chat and deck icon hidden")
        QTimer.singleShot(self.CHAT_RETIRE_MS, retire)

    def _send_limitless_chat(self, text):
        """Chat card -> the match chat on Limitless (through the hidden page)."""
        manager = getattr(self, "limitless_manager", None)
        window = self.chat_window
        if manager is None or not hasattr(manager, "send_chat"):
            if window is not None:
                window.send_result(False, "Couldn't send: Limitless isn't connected.", text)
            return
        manager.send_chat(text, callback=lambda ok, message, text=text:
                          window is not None and window.send_result(ok, message, text))

    def _ping_new_chat(self):
        """New Limitless chat message: a faint yellow glow above the mini GUI
        and the arrow gives a tiny bounce."""
        if not self.isVisible():
            return
        try:
            from PySide6.QtCore import QVariantAnimation
            import math
            if getattr(self, "_chat_glow", None) is None:
                self._chat_glow = ChatPingGlow()
            self._chat_glow.ping(self.geometry())
            anim = getattr(self, "_arrow_bounce", None)
            if anim is None:
                anim = self._arrow_bounce = QVariantAnimation(self)
                anim.setDuration(1100)
                anim.setStartValue(0.0)
                anim.setEndValue(1.0)

                def nudge(t):
                    # Three small hops that die out; 1 px = "ever so slightly".
                    t = float(t)
                    shift = round(math.sin(t * math.pi * 6) * 1.4 * (1.0 - t))
                    self.arrow_label.setContentsMargins(0, max(0, -shift) * 2, 0, max(0, shift) * 2)
                anim.valueChanged.connect(nudge)
                anim.finished.connect(lambda: self.arrow_label.setContentsMargins(0, 0, 0, 0))
            anim.stop()
            anim.start()
        except Exception as exc:
            _dbg(f"chat ping error: {exc}")

    def hud_notifications(self):
        """Our visible popups stacked above the mini GUI, lowest first."""
        notes = []
        for _key, card in self._hud_card_stack():
            try:
                if card is not None and card.isVisible() and card not in notes:
                    notes.append(card)
            except RuntimeError:  # deleted
                pass
        return notes

    def _position_chat_window(self):
        """Place the chat window above the mini stats GUI, right-aligned.

        The chat window's RIGHT edge lines up with the mini GUI's right edge,
        so the chat extends LEFT (up to double the mini GUI width) and never
        runs off the right side of the screen.
        """
        if self.chat_window is None or not self.isVisible():
            return
        try:
            geo = self.geometry()
            chat_w = self.chat_window.width()
            # Right-align: chat's right edge = mini GUI's right edge.
            x = geo.x() + geo.width() - chat_w
            # Allow extending up to double the mini GUI width to the left.
            min_x = geo.x() + geo.width() - (self.width() * 2)
            if x < min_x:
                x = min_x
            if x < 0:
                x = 0
            # The chat always sits above our notifications that stack over
            # the mini GUI (opponent-deck card, friend request popup...).
            top = geo.y()
            for note in self.hud_notifications():
                top = min(top, note.geometry().y())
            y = top - self.chat_window.frameGeometry().height() - 8
            if y < 0:
                y = 0
            self.chat_window.move(x, y)
            icon = getattr(self, "deck_icon", None)
            if icon is not None:
                icon.refresh()
        except Exception as exc:
            _dbg(f"_position_chat_window error: {exc}")

    def _opponent_deck_ready(self):
        manager = getattr(self, "limitless_manager", None)
        if not manager:
            return False
        return manager.opponent_deck_preview(count=0) is not None

    def _open_opponent_deck(self):
        """The deck icon: opens the decklist, or minimizes it if it's up."""
        manager = getattr(self, "limitless_manager", None)
        if not manager:
            return
        window = getattr(manager, "_opp_deck_window", None)
        if window is not None and window.isVisible() and not window.isMinimized():
            window.showMinimized()
        else:
            manager.show_opponent_deck(activate=True)

    def _maybe_start_tutorial(self):
        """First run: the tour, starting at this HUD's arrow (tutorial.py)."""
        try:
            import tutorial
            tutorial.cleanup_stale()
            if self.isVisible() and tutorial.should_offer(self.db):
                tutorial.start(overlay=self)
        except Exception as e:
            _dbg(f"tutorial error: {e}")

    def toggle_stats_dashboard(self):
        """Toggle stats dashboard open/close with smooth arrow animation"""
        if self.stats_window is None or not self.stats_window.isVisible():
            # Opening - animate arrow flip down
            self.animate_arrow("▼")
            self.open_stats_dashboard()
        else:
            # Closing - animate arrow flip up. The window is kept (hidden) so
            # the next open is instant.
            self.animate_arrow("▲")
            self.stats_window.close()
    
    def animate_arrow(self, new_text):
        """Smoothly animate arrow flip"""
        # Simple style update for smooth transition
        QTimer.singleShot(0, lambda: self.arrow_label.setText(new_text))
    
    def _ensure_stats_window(self):
        """Build the dashboard once (hidden). Called a few seconds after the
        hub starts, so clicking the arrow only has to show it."""
        if self.stats_window is None:
            try:
                from StatsUI import StatsWindow
                self.stats_window = StatsWindow(parent_overlay=self)
                self._stats_window_shown_once = False
            except Exception as e:
                _dbg(f"stats window build error: {e}")
        return self.stats_window

    def open_stats_dashboard(self):
        """Open or focus the stats dashboard window"""
        if self.stats_window is None or not getattr(self, "_stats_window_shown_once", False):
            try:
                if self._ensure_stats_window() is None:
                    return
                self._stats_window_shown_once = True

                # Show first so Qt computes the real window size
                self.stats_window.show()

                # Center on game window — GetWindowRect returns physical pixels,
                # stats_window.move() needs logical coords, so divide by DPR.
                if self.game_hwnd:
                    try:
                        gx, gy, gright, gbottom = win32gui.GetWindowRect(self.game_hwnd)
                        dpr = self.devicePixelRatioF() or 1.0
                        gx_l = gx / dpr
                        gy_l = gy / dpr
                        gw_l = (gright - gx) / dpr
                        gh_l = (gbottom - gy) / dpr
                        center_x = int(gx_l + (gw_l - self.stats_window.width()) / 2)
                        center_y = int(gy_l + (gh_l - self.stats_window.height()) / 2)
                        self.stats_window.move(center_x, center_y)
                    except Exception:
                        pass
            except Exception as e:
                _dbg(f"open_stats_dashboard error: {e}")
        else:
            if not self.stats_window.isVisible():
                self.stats_window.show()
            self.stats_window.raise_()
            self.stats_window.activateWindow()

    def suspend_stats_window_tracking(self):
        self.stats_window_tracking_suspended = True

    def resume_stats_window_tracking(self):
        self.stats_window_tracking_suspended = False
        try:
            self.follow_game_window()
        except Exception:
            pass
    
    def update_display(self):
        """Update the stats label and pokeball icon"""
        # Update text
        if _overlay_setting("overlay_show_max_elo", True):
            new_text = f"Elo:{self.current_rank} | Max:{self.max_rank} | {self.wins}-{self.losses}"
        else:
            new_text = f"Elo:{self.current_rank} | {self.wins}-{self.losses}"
        if new_text != self.stats_label.text():
            self.stats_label.setText(new_text)
            # Resize once the layout has seen the new label (the pill shrinks / grows;
            # follow_game_window re-anchors it to the corner).
            QTimer.singleShot(0, self.adjustSize)
        
        # Update pokeball icon based on current Elo
        league = get_league_from_elo(self.current_rank)
        self._ball_league = league
        if not getattr(self, "_ball_shaking", False):
            self._set_ball()


def main():
    """Run the overlay"""
    try:
        import ptcgl_friend
        ptcgl_friend.restore_cursor()  # in case a friend add was cut off with the cursor hidden
    except Exception:
        pass
    app = QApplication(sys.argv)
    import theme
    theme.install(app)  # before any widget: legacy does nothing
    import app_icon
    app_icon.install(app)  # our icon on the taskbar, not Python's
    import infotip
    infotip.install(app)  # two-stage hover tips
    
    # Set application properties
    app.setApplicationName("TCG Live Monitor")
    app.setQuitOnLastWindowClosed(False)
    
    # Create and show overlay
    overlay = MinimalOverlay()
    overlay.show()

    code = app.exec()
    if getattr(overlay, "_restarting", False):
        # Background threads (web views, scans) would keep the process alive,
        # and the monitor only relaunches the overlay once it has exited.
        os._exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
