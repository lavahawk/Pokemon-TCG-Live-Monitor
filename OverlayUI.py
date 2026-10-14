"""
Minimal Game Overlay for Pokemon TCG Live Monitor v2.1
Ultra-compact, professional overlay that follows the game and allows click-through
"""

from version import VERSION

import sys
import os
import time
import win32gui
import win32process
import win32con
import psutil
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
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


def create_pokeball_icon(ball_type="poke"):
    """Create 8-bit style pokeball icons for different leagues"""
    # 12x12 pixel pokeball
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # Keep it pixelated
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    
    # Define colors for each ball type
    colors = {
        "nest": ("#9CC344", "#5C7C28"),      # Nest Ball - Green/Yellow
        "quick": ("#4A9FD8", "#2B5F8C"),     # Quick Ball - Blue
        "poke": ("#E53935", "#C62828"),      # Poke Ball - Red
        "great": ("#1976D2", "#0D47A1"),     # Great Ball - Blue
        "ultra": ("#F9A825", "#F57F17"),     # Ultra Ball - Yellow
        "master": ("#7B1FA2", "#4A148C"),    # Master Ball - Purple
    }
    
    top_color, bottom_color = colors.get(ball_type, colors["poke"])
    
    # Draw black outline (circle)
    painter.setPen(QColor("#000000"))
    painter.setBrush(QColor("#000000"))
    painter.drawEllipse(0, 0, 12, 12)
    
    # Draw top half
    painter.setBrush(QColor(top_color))
    painter.drawChord(1, 1, 10, 10, 0, 180 * 16)
    
    # Draw bottom half (white)
    painter.setBrush(QColor("#F5F5F5"))
    painter.drawChord(1, 1, 10, 10, 180 * 16, 180 * 16)
    
    # Draw middle black line
    painter.setPen(QColor("#000000"))
    painter.drawLine(1, 6, 11, 6)
    
    # Draw center button
    painter.setPen(QColor("#000000"))
    painter.setBrush(QColor("#F5F5F5"))
    painter.drawEllipse(4, 4, 4, 4)
    
    # Inner button detail
    painter.setBrush(QColor("#E0E0E0"))
    painter.drawEllipse(5, 5, 2, 2)
    
    painter.end()
    return pixmap


def get_league_from_elo(elo):
    """Which league ball to show for a ladder rank (thresholds in leagues.py)."""
    from leagues import league_for_rank
    return league_for_rank(elo)


class LimitlessChatWindow(QWidget):
    """Standalone floating chat window for Limitless match chat.

    Completely transparent and click-through (WS_EX_TRANSPARENT |
    WS_EX_LAYERED), positioned above the mini stats GUI. Messages are painted
    directly (no child widgets) so there is no opaque box. Text fades:
      - with HEIGHT: messages higher up (older) are dimmer
      - with TIME: messages older than 10s fade to invisible over 5s
    Action/system messages (check-ins, game reports) are italicized.
    """

    FADE_AFTER_S = 25.0    # full visibility for this long
    FADE_DURATION_S = 10.0   # then fade out over this many seconds
    MAX_MESSAGES = 8
    WIDTH = 300

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LimitlessChat")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.messages = []  # [{text, type, ts(datetime)}]
        self._hovered = False
        # Repaint regularly so time-based fading animates smoothly.
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(100)
        self._fade_timer.timeout.connect(self.update)
        self._fade_timer.start()

    # --- click-through -----------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        try:
            import win32gui, win32con, win32api
            hwnd = int(self.winId())
            style = win32api.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32api.SetWindowLong(
                hwnd, win32con.GWL_EXSTYLE,
                style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT,
            )
        except Exception:
            pass

    # --- data --------------------------------------------------------------
    def set_messages(self, messages, own_name=""):
        """Replace the message list.

        Each item: {text, type, sender, ts(ISO str)}. Messages whose sender
        matches own_name are right-aligned (yours); others left-aligned
        (opponent's); actions centered.
        """
        now = datetime.now()
        self.own_name = (own_name or "").strip().lower()
        self.messages = []
        for msg in messages[-self.MAX_MESSAGES:]:
            text = str(msg.get("text") or "").strip()
            if not text:
                continue
            mtype = str(msg.get("type") or "chat")
            sender = str(msg.get("sender") or "").strip()
            try:
                ts = datetime.fromisoformat(str(msg.get("ts") or ""))
            except Exception:
                ts = now
            self.messages.append({"text": text, "type": mtype, "sender": sender, "ts": ts})
        self._relayout()
        if self.messages:
            self.show()
        else:
            self.hide()

    def _is_own(self, msg):
        """True if the message was sent by the player (right-aligned)."""
        sender = (msg.get("sender") or "").strip().lower()
        return bool(sender) and bool(self.own_name) and sender == self.own_name

    def _relayout(self):
        """Compute required height from wrapped text and resize the window."""
        if not self.messages:
            self.hide()
            return
        fm = self.fontMetrics()
        font = self.font()
        line_h = fm.height() + 2
        total_h = 0
        for msg in self.messages:
            f = QFont(font)
            f.setItalic(msg["type"] == "action")
            lines = 0
            remaining = msg["text"]
            # Simple greedy word-wrap to count lines.
            words = remaining.split()
            cur = ""
            for word in words:
                trial = (cur + " " + word).strip()
                if fm.horizontalAdvance(trial) > self.WIDTH - 16 and cur:
                    lines += 1
                    cur = word
                else:
                    cur = trial
            lines += 1
            msg["lines"] = lines
            total_h += lines * line_h + 4
        self.setFixedSize(self.WIDTH, total_h + 8)
        self.update()

    # --- painting ----------------------------------------------------------
    def paintEvent(self, event):
        if not self.messages:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self.font()
        base_font_size = 9
        line_h = base_font_size + 6
        now = datetime.now()
        total = len(self.messages)
        y = 4.0
        for index, msg in enumerate(self.messages):
            # Height fade: newest (bottom) = 1.0, oldest (top) = 0.35.
            height_alpha = 1.0 - (index / max(1, total)) * 0.65
            # Time fade: full for 10s, then fade out over 5s.
            age = (now - msg["ts"]).total_seconds()
            if age <= self.FADE_AFTER_S:
                time_alpha = 1.0
            else:
                time_alpha = max(0.0, 1.0 - (age - self.FADE_AFTER_S) / self.FADE_DURATION_S)
            alpha = height_alpha * time_alpha
            lines = msg.get("lines", 1)
            if alpha <= 0.01:
                y += lines * line_h + 4
                continue
            f = QFont(font)
            f.setPixelSize(base_font_size)
            f.setItalic(msg["type"] == "action")
            painter.setFont(f)
            # Conversation alignment: yours right, opponent's left,
            # actions centered — like a normal chat.
            if msg["type"] == "action":
                align = Qt.AlignmentFlag.AlignHCenter
                x = 4
            elif self._is_own(msg):
                align = Qt.AlignmentFlag.AlignRight
                x = 4
            else:
                align = Qt.AlignmentFlag.AlignLeft
                x = 4
            # Slight color tint for your own messages.
            if self._is_own(msg):
                color = QColor(190, 214, 255, int(255 * alpha))
            else:
                color = QColor(228, 238, 245, int(255 * alpha))
            painter.setPen(color)
            rect = QRectF(x, y, self.WIDTH - 8, lines * line_h)
            painter.drawText(
                rect,
                int(align | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
                msg["text"],
            )
            y += lines * line_h + 4
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
        _dbg("__init__ complete")
    
    def _poll_deck_confirm(self):
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
                        self.deck_popup = DeckConfirmPopup(self.db)
                    self.deck_popup.offer(request, anchor)
                    # HUD buddy: celebrate a win, mope after a loss (once per battle)
                    if self.pet is not None and request.get("battle_id") != getattr(self, "_pet_reacted", None):
                        self._pet_reacted = request.get("battle_id")
                        self.pet.react(request.get("result"))
                    _dbg(f"deck popup: battle {request.get('battle_id')} {request.get('deck')!r} "
                         f"({request.get('source')}, needs_input={request.get('needs_input')})")
            if self.deck_popup is not None:
                self.deck_popup.tick(menu_seen_at(), anchor, self.isVisible())
                self._position_chat_window()
        except Exception as exc:
            _dbg(f"_poll_deck_confirm error: {exc}")
        self._poll_game_session()
        self._poll_pet()

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
            from deck_confirm import battle_started_at
            started = battle_started_at()
            if self.pet is None:
                from pet import PetWidget
                self.pet = PetWidget(species)
                self._pet_battle_seen = started  # don't react to a battle from before
            else:
                self.pet.set_species(species)
            if started > getattr(self, "_pet_battle_seen", 0.0):
                self._pet_battle_seen = started
                if time.time() - started < 60:
                    self.pet.battle_start()
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
            # Hide overlay if game is minimized
            if win32gui.IsIconic(hwnd):
                if self.isVisible():
                    self.hide()
                return

            # GetWindowRect returns physical pixels (DPI-aware process).
            # self.width()/height() are logical pixels. Multiply by DPR to get
            # physical dimensions so both values are in the same unit.
            _, _, game_right, game_bottom = win32gui.GetWindowRect(hwnd)

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
                self._position_reset_popup()
        except Exception as e:
            _dbg(f"follow_game_window exception: {e}")
    
    def init_ui(self):
        """Initialize minimal UI"""
        # Window properties - clickable but stays on top
        self.setWindowTitle("TCG Monitor")
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
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        # The Limitless match chat lives in its own standalone window
        # (LimitlessChatWindow) positioned ABOVE this mini GUI — it is fully
        # transparent, click-through, and fades with height and time.
        self.chat_window = None

        # Stats display with pokeball icon
        stats_layout = QHBoxLayout()
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(4)
        
        # Pokeball icon label
        self.ball_icon = QLabel()
        self.ball_icon.setFixedSize(12, 12)
        # Double-click the ball: recall / send out the HUD buddy (pet.py)
        self.ball_icon.mouseDoubleClickEvent = lambda e: getattr(self, "pet", None) is not None and self.pet.toggle_ball()
        stats_layout.addWidget(self.ball_icon)
        
        # Stats text label — double-click opens a mini reset popup
        self.stats_label = QLabel("Elo:-- | Max:-- | 0-0")
        self.stats_label.setObjectName("stats")
        self.stats_label.setToolTip("Double-click to reset today's W/L count")
        self.stats_label.mouseDoubleClickEvent = lambda e: self.confirm_reset_today_stats()
        stats_layout.addWidget(self.stats_label)
        
        # Small arrow indicator (clickable)
        self.arrow_label = QLabel("▲")
        self.arrow_label.setObjectName("arrow")
        self.arrow_label.setFixedSize(10, 12)
        self.arrow_label.mousePressEvent = lambda e: self.toggle_stats_dashboard()
        stats_layout.addWidget(self.arrow_label)
        
        layout.addLayout(stats_layout)
        
        # Apply minimal styling
        self.apply_style()
        
        # Let the widget size itself to fit content
        self.adjustSize()
    
    def apply_style(self):
        """Apply minimal, professional styling"""
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
                font-size: 11px;
                font-weight: 500;
                background-color: transparent;
            }
            QLabel#arrow {
                color: #C8C8C8;
                font-family: 'Segoe UI', Arial;
                font-size: 9px;
                background-color: transparent;
            }
            QLabel#arrow:hover {
                color: #FFFFFF;
            }
        """)
    
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
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = size / 2.0 - 0.5
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
                    messages.append({"text": text, "type": mtype, "sender": sender, "ts": ts})
            if not messages:
                self.limitless_chat_state = {}
                if self.chat_window is not None:
                    self.chat_window.hide()
                return

            self.limitless_chat_state = state
            # Lazily create the standalone chat window (fully transparent,
            # click-through, fades with height and time) and position it
            # directly above this mini GUI.
            if self.chat_window is None:
                self.chat_window = LimitlessChatWindow()
            # Pass the player's username so their own messages are
            # right-aligned like a normal conversation.
            try:
                from app_settings import load_username
                own_name = load_username() or ""
            except Exception:
                own_name = ""
            self.chat_window.set_messages(messages, own_name=own_name)
            self._position_chat_window()
        except Exception as exc:
            _dbg(f"update_limitless_chat error: {exc}")

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
            top = geo.y()
            # Stack above the opponent-deck card while it is showing.
            popup = getattr(self, "deck_popup", None)
            if popup is not None and popup.isVisible():
                top = min(top, popup.geometry().y())
            y = top - self.chat_window.height() - 8
            if y < 0:
                y = 0
            self.chat_window.move(x, y)
        except Exception as exc:
            _dbg(f"_position_chat_window error: {exc}")

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
        pokeball = create_pokeball_icon(league)
        self.ball_icon.setPixmap(pokeball)


def main():
    """Run the overlay"""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("TCG Live Monitor")
    app.setQuitOnLastWindowClosed(False)
    
    # Create and show overlay
    overlay = MinimalOverlay()
    overlay.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
