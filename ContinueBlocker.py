"""
Continue-Button Blocker for Pokemon TCG Live

Shows a small themed overlay over the game's Continue button while the
battle-end auto-clicker exports the battle log. Because the blocker is a
topmost window, it physically intercepts clicks on the Continue button —
no mouse hooks needed.

Theme matches the mini GUI (OverlayUI.py): dark translucent card,
#3E4A52 border, pokeball glyph, subtle pulse.

Usage (launched by TCGLiveMonitor):
    python ContinueBlocker.py --x 0.50 --y 0.88 --w 0.30 --h 0.08
(x/y/w/h are relative to the game window; defaults below)

Auto-exits after BLOCKER_MAX_LIFE seconds as a failsafe, or when killed
by the monitor after the export completes.
"""

import sys
import time
import argparse
import os

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QHBoxLayout, QPushButton

import win32gui

BLOCKER_MAX_LIFE = 30  # failsafe: never linger longer than this

# Default Continue-button region, relative to the game window.
# Centered directly below the BATTLE LOG button (~50% x, ~81% y).
DEFAULT_REL = {"x": 0.50, "y": 0.935, "w": 0.26, "h": 0.075}


def _dbg(msg):
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logs", "blocker_debug.log"), "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _make_pokeball_pixmap(size=14):
    """Tiny flat pokeball matching the mini GUI's glyph style."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, False)  # keep the 8-bit look
    accent = QColor("#FFD9D9")
    dark = QColor("#3A3A3A")
    s = size
    half = s // 2
    # top half
    p.fillRect(0, 0, s, half, accent)
    # bottom half
    p.fillRect(0, half, s, s - half, dark)
    # center band + button
    p.fillRect(0, half - 1, s, 2, QColor("#1A1A1A"))
    p.fillRect(half - 2, half - 2, 4, 4, QColor("#E9E9E9"))
    p.end()
    return pm


class _ProgressStrip(QWidget):
    """Slim indeterminate progress bar: a soft glow segment glides along a
    dim track. Fixed size, so nothing shifts while it animates."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self._pos = 0.0  # 0..1 head position of the glow

    def advance(self):
        # Ease toward 1.0, then wrap with a brief fade at the ends.
        self._pos += 0.018
        if self._pos > 1.15:
            self._pos = -0.15
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # dim track
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        # moving glow segment (clipped to the track)
        seg_w = int(w * 0.30)
        x = int(self._pos * (w + seg_w)) - seg_w
        p.save()
        p.setClipRect(0, 0, w, h)
        grad_x0, grad_x1 = x, x + seg_w
        from PySide6.QtGui import QLinearGradient
        g = QLinearGradient(grad_x0, 0, grad_x1, 0)
        g.setColorAt(0.0, QColor(159, 178, 192, 0))
        g.setColorAt(0.5, QColor(159, 178, 192, 200))
        g.setColorAt(1.0, QColor(159, 178, 192, 0))
        p.setBrush(g)
        p.drawRoundedRect(max(x, 0), 0, min(seg_w, w - max(x, 0)), h, h / 2, h / 2)
        p.restore()
        p.end()


class ContinueBlocker(QWidget):
    def __init__(self, rel):
        super().__init__()
        self.rel = rel
        self.born = time.time()
        self._pulse = 0.0
        self._pulse_dir = 1

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 4, 4)
        layout.setSpacing(6)

        self.label = QLabel("Saving battle log")
        self.label.setObjectName("blockLabel")
        layout.addWidget(self.label, 1)

        self.strip = _ProgressStrip()
        layout.addWidget(self.strip, 1)

        # Dim dismiss button — in case the blocker misbehaves or the user
        # needs to press Continue anyway. Styled like the reset-popup X.
        self.close_btn = QPushButton("\u00d7")
        self.close_btn.setObjectName("blockClose")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

        # Font matches the mini GUI's stats label ('Segoe UI', 11px, #DCDCDC).
        self.setStyleSheet("""
            QLabel#blockLabel {
                color: #DCDCDC;
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
                font-weight: 500;
                background: transparent;
            }
            QPushButton#blockClose {
                color: #6A6A6A;
                background-color: transparent;
                border: none;
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
                font-weight: 700;
                padding: 0;
            }
            QPushButton#blockClose:hover {
                color: #FFFFFF;
            }
        """)

        # Follow the game window; animate the strip; failsafe exit.
        self.follow_timer = QTimer(self)
        self.follow_timer.timeout.connect(self._follow_game)
        self.follow_timer.start(200)

        self.strip_timer = QTimer(self)
        self.strip_timer.timeout.connect(self.strip.advance)
        self.strip_timer.start(16)  # ~60fps glide

        self.life_timer = QTimer(self)
        self.life_timer.timeout.connect(self.close)
        self.life_timer.start(int(BLOCKER_MAX_LIFE * 1000))

        self._follow_game()

    def _find_game_rect(self):
        # RankDetector resolves the real game window (FindWindow alone can
        # return a stale/shifted rect for the UWP-hosted game).
        try:
            from RankDetector import RankDetector
            gw = RankDetector().find_game_window()
            if not gw:
                return None
            l, t = gw["left"], gw["top"]
            r, b = l + gw["width"], t + gw["height"]
        except Exception:
            hwnd = win32gui.FindWindow(None, "Pokemon TCG Live")
            if not hwnd or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return None
            try:
                l, t, r, b = win32gui.GetWindowRect(hwnd)
            except Exception:
                return None
        if r - l <= 0 or b - t <= 0:
            return None
        return l, t, r, b

    def _follow_game(self):
        if time.time() - self.born > BLOCKER_MAX_LIFE:
            self.close()
            return
        rect = self._find_game_rect()
        if rect is None:
            if self.isVisible():
                _dbg("game rect not found — hiding")
                self.hide()
            return
        l, t, r, b = rect
        gw, gh = r - l, b - t
        w = int(gw * self.rel["w"])
        h = int(gh * self.rel["h"])
        x = l + int(gw * self.rel["x"]) - w // 2
        y = t + int(gh * self.rel["y"]) - h // 2
        # Position in PHYSICAL pixels via win32 — Qt setGeometry works in
        # logical pixels and gets DPI-scaled away from the intended spot.
        # HWND_TOPMOST keeps the blocker above the fullscreen game so it
        # physically intercepts clicks on Continue.
        try:
            import win32con
            win32gui.SetWindowPos(
                int(self.winId()), win32con.HWND_TOPMOST,
                x, y, w, h, win32con.SWP_NOACTIVATE,
            )
        except Exception as exc:
            _dbg(f"SetWindowPos failed: {exc}")
        self.show()
        if not getattr(self, "_logged_pos", False):
            _dbg(f"game=({l},{t},{r},{b}) blocker=({x},{y},{w},{h})")
            self._logged_pos = True

    def paintEvent(self, event):
        from PySide6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        # Card body
        p.fillPath(path, QColor(18, 18, 18, 235))
        # Subtle top inner highlight for depth
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 10))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -2, -self.height() // 2), 7, 7)
        # Border
        p.setBrush(Qt.NoBrush)
        p.setPen(QColor(0x3E, 0x4A, 0x52))
        p.drawPath(path)
        p.end()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=float, default=DEFAULT_REL["x"])
    ap.add_argument("--y", type=float, default=DEFAULT_REL["y"])
    ap.add_argument("--w", type=float, default=DEFAULT_REL["w"])
    ap.add_argument("--h", type=float, default=DEFAULT_REL["h"])
    args = ap.parse_args()

    _dbg(f"blocker started rel=({args.x}, {args.y}, {args.w}, {args.h})")
    app = QApplication.instance() or QApplication(sys.argv)
    blocker = ContinueBlocker({"x": args.x, "y": args.y, "w": args.w, "h": args.h})
    blocker.show()
    app.exec()
    _dbg("blocker exited")


if __name__ == "__main__":
    main()
