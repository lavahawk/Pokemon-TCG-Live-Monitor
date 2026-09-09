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
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QHBoxLayout, QPushButton

import win32gui

BLOCKER_MAX_LIFE = 30  # failsafe: never linger longer than this

# Default Continue-button region, relative to the game window.
# Centered directly below the BATTLE LOG button (~50% x, ~81% y).
DEFAULT_REL = {"x": 0.50, "y": 0.955, "w": 0.32, "h": 0.11}


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


class ContinueBlocker(QWidget):
    def __init__(self, rel):
        super().__init__()
        self.rel = rel
        self.born = time.time()
        self._dash_offset = 0.0  # animated border phase
        self._opacity = 0.0      # current window opacity (fade state)
        self._fade_target = 0.0
        self._closing = False
        self.setWindowOpacity(0.0)

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

        # Dim dismiss button — in case the blocker misbehaves or the user
        # needs to press Continue anyway. Styled like the reset-popup X.
        self.close_btn = QPushButton("\u00d7")
        self.close_btn.setObjectName("blockClose")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(lambda: self.dismiss(close_after=True))
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

        # Follow the game window; animate the border + opacity; failsafe exit.
        self.follow_timer = QTimer(self)
        self.follow_timer.timeout.connect(self._follow_game)
        self.follow_timer.start(200)

        self.border_timer = QTimer(self)
        self.border_timer.timeout.connect(self._border_tick)
        self.border_timer.start(33)  # ~30fps: smooth, low CPU

        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self._fade_tick)
        self.fade_timer.start(16)

        self.life_timer = QTimer(self)
        self.life_timer.timeout.connect(lambda: self.dismiss(close_after=True))
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
            _dbg("failsafe lifetime reached — fading out")
            self.dismiss(close_after=True)
            return
        rect = self._find_game_rect()
        if rect is None:
            if self.isVisible() or self._fade_target > 0.0:
                _dbg("game rect not found — fading out")
                self._begin_fade_out()
            return
        l, t, r, b = rect
        gw, gh = r - l, b - t
        w = int(gw * self.rel["w"])
        h = int(gh * self.rel["h"])
        x = l + int(gw * self.rel["x"]) - w // 2
        y = t + int(gh * self.rel["y"]) - h // 2
        # Only reposition when the rect actually changed — calling
        # SetWindowPos every tick with 1px rounding jitter makes the box
        # visibly tremble. EXCEPTION: Qt shrinks the native window to its
        # layout sizeHint after show(), so verify the REAL rect each tick
        # and re-assert if it drifted.
        new_geom = (x, y, w, h)
        actual = None
        try:
            al, at, ar, ab = win32gui.GetWindowRect(int(self.winId()))
            actual = (al, at, ar - al, ab - at)
        except Exception:
            pass
        if getattr(self, "_last_geom", None) != new_geom or actual != new_geom:
            # Position in PHYSICAL pixels via win32 — Qt setGeometry works in
            # logical pixels and gets DPI-scaled away from the intended spot.
            # HWND_TOPMOST keeps the blocker above the fullscreen game so it
            # physically intercepts clicks on Continue.
            try:
                import win32con
                if not self.isVisible():
                    self.show()
                win32gui.SetWindowPos(
                    int(self.winId()), win32con.HWND_TOPMOST,
                    x, y, w, h, win32con.SWP_NOACTIVATE,
                )
                self._last_geom = new_geom
            except Exception as exc:
                _dbg(f"SetWindowPos failed: {exc}")
        if not self.isVisible() and not self._closing:
            self.show()
            self._begin_fade_in()  # materialize from thin air
        if not getattr(self, "_logged_pos", False):
            _dbg(f"game=({l},{t},{r},{b}) blocker=({x},{y},{w},{h})")
            self._logged_pos = True

    def _border_tick(self):
        # Advance the comet along the border (0..1 around the perimeter).
        self._comet_pos = (getattr(self, "_comet_pos", 0.0) + 0.0035) % 1.0
        self.update()

    def _fade_tick(self):
        """Ease window opacity toward the target (fade in/out).
        Uses an exponential approach for a silky, professional feel.
        Once a fade-out completes, the window actually closes/hides."""
        target = self._fade_target
        cur = self._opacity
        if abs(target - cur) < 0.01:
            self._opacity = target
        else:
            # exponential ease: fast start, gentle settle
            self._opacity = cur + (target - cur) * 0.18
        self.setWindowOpacity(self._opacity)
        if target == 0.0 and self._opacity <= 0.01:
            if self._closing:
                self.fade_timer.stop()
                self.close()
            else:
                self.hide()

    def _begin_fade_in(self):
        self._fade_target = 1.0
        self._closing = False

    def _begin_fade_out(self, close_after=False):
        self._fade_target = 0.0
        self._closing = close_after

    def dismiss(self, close_after=False):
        """User- or system-initiated fade-out. Stops the follow timer so the
        window isn't re-shown right after being dismissed."""
        self.follow_timer.stop()
        self._begin_fade_out(close_after=close_after)

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
        # Static dim border
        p.setBrush(Qt.NoBrush)
        dim = QPen(QColor(0x3E, 0x4A, 0x52), 1)
        p.setPen(dim)
        p.drawPath(path)
        # Comet: a single soft glowing head with a fading trail glides
        # around the border — subtle, premium, not busy.
        head = self._comet_pos = getattr(self, "_comet_pos", 0.0)
        TRAIL = 14
        for i in range(TRAIL, 0, -1):
            frac = (head - i * 0.006) % 1.0
            pt = path.pointAtPercent(frac)
            fade = 1.0 - i / TRAIL
            radius = 1.2 + 2.2 * fade
            color = QColor(int(159 + 40 * fade), int(178 + 30 * fade), 192, int(230 * fade))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(pt, radius, radius)
        # bright head
        hp = path.pointAtPercent(head)
        p.setBrush(QColor(233, 243, 255))
        p.drawEllipse(hp, 3.2, 3.2)
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
