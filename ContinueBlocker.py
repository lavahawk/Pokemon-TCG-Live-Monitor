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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QHBoxLayout, QPushButton

import win32gui

BLOCKER_MAX_LIFE = 30  # failsafe: never linger longer than this
DISMISS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logs", ".blocker_dismiss")
READY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logs", ".blocker_ready")
SHOW_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logs", ".blocker_show")
STANDBY_MAX_LIFE = 3 * 3600  # a hidden standby copy never outlives a long session

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


class ContinueBlocker(QWidget):
    def __init__(self, rel, standby=False, parent_pid=None):
        super().__init__()
        self.rel = rel
        self.born = time.time()
        self.parent_pid = parent_pid
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
        self.border_timer = QTimer(self)
        self.border_timer.timeout.connect(self._border_tick)
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self._fade_tick)
        # Watch for the monitor's dismiss signal (export hit the clipboard).
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.timeout.connect(self._check_dismiss_signal)
        self.life_timer = QTimer(self)
        self.life_timer.timeout.connect(lambda: self.dismiss(close_after=True))

        if standby:
            # Pre-warmed while the game is open: Qt is already loaded, so
            # showing takes one poll (<= 10 ms) instead of a 1-2 s process start.
            _dbg("standby: waiting for show signal")
            # Pay the one-time costs now: game-window lookup, and the first
            # show() (~320 ms of Qt window/paint setup; later shows ~10 ms),
            # done fully transparent and off-screen.
            self._find_game_rect()
            QTimer.singleShot(0, self._warm_up)
            self.show_timer = QTimer(self)
            self.show_timer.timeout.connect(self._check_show_signal)
            self.show_timer.start(10)  # one stat() per tick: negligible CPU
            self.parent_timer = QTimer(self)
            self.parent_timer.timeout.connect(self._check_parent)
            self.parent_timer.start(5000)
        else:
            self.activate()

    def activate(self):
        self.born = time.time()
        self.follow_timer.start(200)
        self.border_timer.start(33)  # ~30fps: smooth, low CPU
        self.fade_timer.start(16)
        self.dismiss_timer.start(100)
        # Start mostly opaque: the box must stop a click on Continue from the
        # first frame, so only the last stretch of the fade-in is animated.
        self._opacity = max(self._opacity, 0.6)
        self.setWindowOpacity(self._opacity)
        self.life_timer.start(int(BLOCKER_MAX_LIFE * 1000))
        self._follow_game()
        self._begin_fade_in()

    def _warm_up(self):
        self.setWindowOpacity(0.0)
        self.move(-20000, -20000)
        self.show()
        self.hide()

    def _check_show_signal(self):
        if os.path.exists(SHOW_FILE):
            self.show_timer.stop()
            try:
                os.remove(SHOW_FILE)
            except Exception:
                pass
            _dbg("standby: show signal received")
            self.activate()
        elif time.time() - self.born > STANDBY_MAX_LIFE:
            _dbg("standby: max life reached - exit")
            os._exit(0)

    def _check_parent(self):
        """Standby copies exit when the monitor that started them is gone."""
        if not self.parent_pid or not self.show_timer.isActive():
            return
        try:
            import psutil
            if not psutil.pid_exists(self.parent_pid):
                _dbg("standby: monitor gone - exit")
                os._exit(0)
        except Exception:
            pass

    def _check_dismiss_signal(self):
        """Fade out the moment the monitor signals the export happened."""
        try:
            if os.path.exists(DISMISS_FILE):
                self.dismiss(close_after=True)
        except Exception:
            pass

    def _find_game_rect(self):
        # Cached, exact-title window lookup (no OCR/mss objects per tick).
        if not hasattr(self, "_window_cache"):
            from game_window import GameWindowCache
            self._window_cache = GameWindowCache(refresh_s=2.0)
        gw = self._window_cache.rect()
        if not gw:
            return None
        l, t = gw["left"], gw["top"]
        return l, t, l + gw["width"], t + gw["height"]

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
                if not getattr(self, "_ready_signalled", False):
                    # The monitor waits for this before clicking anything,
                    # so the Continue button is covered before the sequence.
                    self._ready_signalled = True
                    try:
                        with open(READY_FILE, "w", encoding="utf-8") as f:
                            f.write(str(time.time()))
                    except Exception:
                        pass
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
        self._comet_pos = (getattr(self, "_comet_pos", 0.0) + 0.0028) % 1.0
        self.update()

    def _fade_tick(self):
        """Ease window opacity toward the target (fade in/out).
        Uses an exponential approach for a silky, professional feel.
        Once a fade-out completes, the process HARD-EXITS — no lingering
        Qt timers, no polling, zero footprint after dismissal."""
        target = self._fade_target
        cur = self._opacity
        if abs(target - cur) < 0.01:
            self._opacity = target
        else:
            # exponential ease: fast start, gentle settle (snappier fade-in so
            # the Continue button is covered almost immediately)
            self._opacity = cur + (target - cur) * (0.4 if target > cur else 0.18)
        self.setWindowOpacity(self._opacity)
        if target == 0.0 and self._opacity <= 0.01:
            if self._closing:
                _dbg("fade-out complete — hard exit")
                os._exit(0)  # kill ALL timers/threads instantly
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
        TRAIL = 10
        for i in range(TRAIL, 0, -1):
            frac = (head - i * 0.008) % 1.0
            pt = path.pointAtPercent(frac)
            fade = 1.0 - i / TRAIL
            radius = 1.0 + 1.8 * fade
            color = QColor(int(159 + 40 * fade), int(178 + 30 * fade), 192, int(210 * fade))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(pt, radius, radius)
        # bright head
        hp = path.pointAtPercent(head)
        p.setBrush(QColor(233, 243, 255))
        p.drawEllipse(hp, 2.8, 2.8)
        p.end()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=float, default=DEFAULT_REL["x"])
    ap.add_argument("--y", type=float, default=DEFAULT_REL["y"])
    ap.add_argument("--w", type=float, default=DEFAULT_REL["w"])
    ap.add_argument("--h", type=float, default=DEFAULT_REL["h"])
    ap.add_argument("--standby", action="store_true", help="start hidden; show on the monitor's signal")
    ap.add_argument("--parent", type=int, default=None, help="monitor PID (standby exits when it is gone)")
    args = ap.parse_args()

    _dbg(f"blocker started rel=({args.x}, {args.y}, {args.w}, {args.h}) standby={args.standby}")
    # Qt6 already makes the process per-monitor DPI aware.
    app = QApplication.instance() or QApplication(sys.argv)
    blocker = ContinueBlocker({"x": args.x, "y": args.y, "w": args.w, "h": args.h},
                              standby=args.standby, parent_pid=args.parent)
    if not args.standby:
        blocker.show()
    app.exec()
    _dbg("blocker exited")


if __name__ == "__main__":
    main()
