"""
Minimal Game Overlay for Pokemon TCG Live Monitor v2.1
Ultra-compact, professional overlay that follows the game and allows click-through
"""

VERSION = "2.1"

import sys
import os
import win32gui
import win32process
import win32con
import psutil
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QPainter, QColor
from BattleDatabase import BattleDatabase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "Logs")

# --- DEBUG LOGGING (internal only) ---
import datetime as _dt
_DBG_FILE = os.path.join(BASE_DIR, ".overlay_debug.log")
def _dbg(msg):
    line = f"[{_dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}\n"
    with open(_DBG_FILE, "a", encoding="utf-8") as _f:
        _f.write(line)
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
    """Determine which league ball to show based on Elo"""
    try:
        elo_num = int(elo)
        if elo_num >= 550:
            return "master"
        elif elo_num >= 390:
            return "ultra"
        elif elo_num >= 230:
            return "great"
        elif elo_num >= 110:
            return "poke"
        elif elo_num >= 30:
            return "quick"
        else:
            return "nest"
    except:
        return "poke"  # Default


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
        _dbg("__init__ complete")
    
    def check_monitor_running(self):
        """Check if TCGLiveMonitor.py is still running via PID file"""
        try:
            pid_file = os.path.join(BASE_DIR, '.monitor_pid')
            monitor_running = False
            if os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    content = f.read().strip()
                pid = int(content.split()[0]) if content else 0
                monitor_running = psutil.pid_exists(pid) if pid else False

            if not monitor_running and self.parent_monitor_running:
                _dbg("Monitor PID gone - quitting overlay")
                print("Monitor closed, shutting down overlay...")
                QApplication.quit()

            self.parent_monitor_running = monitor_running
        except Exception:
            pass  # never block the event loop

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

            _dbg(f"pos: game=({game_right},{game_bottom}) dpr={dpr} phys={phys_w}x{phys_h} -> ({x},{y})")

            if not self.isVisible():
                self.show()

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

        self.chat_frame = QFrame()
        self.chat_frame.setObjectName("chatPanel")
        self.chat_frame.hide()

        chat_layout = QVBoxLayout(self.chat_frame)
        chat_layout.setContentsMargins(8, 7, 8, 7)
        chat_layout.setSpacing(4)

        self.chat_title_label = QLabel("Limitless Match")
        self.chat_title_label.setObjectName("chatTitle")
        chat_layout.addWidget(self.chat_title_label)

        self.chat_subtitle_label = QLabel("")
        self.chat_subtitle_label.setObjectName("chatSubtitle")
        self.chat_subtitle_label.setWordWrap(True)
        self.chat_subtitle_label.hide()
        chat_layout.addWidget(self.chat_subtitle_label)

        self.chat_messages_label = QLabel("")
        self.chat_messages_label.setObjectName("chatMessages")
        self.chat_messages_label.setWordWrap(True)
        self.chat_messages_label.setTextFormat(Qt.TextFormat.PlainText)
        chat_layout.addWidget(self.chat_messages_label)

        layout.addWidget(self.chat_frame)
        
        # Stats display with pokeball icon
        stats_layout = QHBoxLayout()
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(4)
        
        # Pokeball icon label
        self.ball_icon = QLabel()
        self.ball_icon.setFixedSize(12, 12)
        stats_layout.addWidget(self.ball_icon)
        
        # Stats text label
        self.stats_label = QLabel("Elo:-- | Max:-- | 0-0")
        self.stats_label.setObjectName("stats")
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
            QFrame#chatPanel {
                background-color: rgba(18, 18, 18, 0.92);
                border: 1px solid #3E4A52;
                border-radius: 6px;
            }
            QLabel#stats {
                color: #DCDCDC;
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
                font-weight: 500;
                background-color: transparent;
            }
            QLabel#chatTitle {
                color: #E9F3FF;
                font-family: 'Segoe UI', Arial;
                font-size: 10px;
                font-weight: 700;
                background-color: transparent;
            }
            QLabel#chatSubtitle {
                color: #9FB2C0;
                font-family: 'Segoe UI', Arial;
                font-size: 9px;
                background-color: transparent;
            }
            QLabel#chatMessages {
                color: #D9E3EA;
                font-family: 'Segoe UI', Arial;
                font-size: 9px;
                line-height: 1.25;
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
            self.wins, self.losses = self.db.get_today_stats()
            
            # Update display
            self.update_display()

        except Exception as e:
            _dbg(f"load_stats error: {e}")

    def update_limitless_chat(self, payload):
        try:
            state = payload if isinstance(payload, dict) else {}
            messages = [str(msg).strip() for msg in (state.get("messages") or []) if str(msg).strip()]
            if not messages:
                self.limitless_chat_state = {}
                self.chat_frame.hide()
                self.adjustSize()
                return

            self.limitless_chat_state = state
            self.chat_title_label.setText((state.get("header") or "Limitless Match")[:64])
            subtitle = (state.get("subtitle") or "").strip()
            if subtitle:
                self.chat_subtitle_label.setText(subtitle[:96])
                self.chat_subtitle_label.show()
            else:
                self.chat_subtitle_label.hide()
            self.chat_messages_label.setText("\n".join(messages[-6:]))
            self.chat_frame.setFixedWidth(280)
            self.chat_frame.show()
            self.adjustSize()
            self.follow_game_window()
        except Exception as exc:
            _dbg(f"update_limitless_chat error: {exc}")
    
    def toggle_stats_dashboard(self):
        """Toggle stats dashboard open/close with smooth arrow animation"""
        if self.stats_window is None or not self.stats_window.isVisible():
            # Opening - animate arrow flip down
            self.animate_arrow("▼")
            self.open_stats_dashboard()
        else:
            # Closing - animate arrow flip up
            self.animate_arrow("▲")
            self.stats_window.close()
            self.stats_window = None
    
    def animate_arrow(self, new_text):
        """Smoothly animate arrow flip"""
        # Simple style update for smooth transition
        QTimer.singleShot(0, lambda: self.arrow_label.setText(new_text))
    
    def open_stats_dashboard(self):
        """Open or focus the stats dashboard window"""
        if self.stats_window is None:
            try:
                from StatsUI import StatsWindow
                self.stats_window = StatsWindow(parent_overlay=self)

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
        new_text = f"Elo:{self.current_rank} | Max:{self.max_rank} | {self.wins}-{self.losses}"
        self.stats_label.setText(new_text)
        
        # Update pokeball icon based on current Elo
        league = get_league_from_elo(self.current_rank)
        pokeball = create_pokeball_icon(league)
        self.ball_icon.setPixmap(pokeball)
    
    def calculate_session_stats(self):
        """Calculate wins/losses from today's logs"""
        try:
            # Look for TCGExampleSheet.xlsx or battle_results*.xlsx
            results_file = os.path.join(BASE_DIR, "TCGExampleSheet.xlsx")
            
            if not os.path.exists(results_file):
                # Fallback: search for battle_results*.xlsx
                for file in os.listdir(BASE_DIR):
                    if file.startswith("battle_results") and file.endswith(".xlsx"):
                        results_file = os.path.join(BASE_DIR, file)
                        break
            
            if not os.path.exists(results_file):
                print("Excel file not found")
                return 0, 0
            
            # Read all sheets and count wins/losses
            import pandas as pd
            xl_file = pd.ExcelFile(results_file)
            
            total_wins = 0
            total_losses = 0
            
            # Read all sheets (each deck has its own sheet)
            for sheet_name in xl_file.sheet_names:
                if sheet_name == "Limitless Meta":  # Skip the meta sheet
                    continue
                
                try:
                    df = pd.read_excel(results_file, sheet_name=sheet_name)
                    
                    # Count wins/losses in this sheet
                    if 'Result' in df.columns:
                        wins = len(df[df['Result'].str.upper().str.contains('WIN', na=False)])
                        losses = len(df[df['Result'].str.upper().str.contains('LOSS', na=False)])
                        total_wins += wins
                        total_losses += losses
                except Exception as e:
                    print(f"Error reading sheet {sheet_name}: {e}")
                    continue
            
            return total_wins, total_losses
            
        except Exception as e:
            print(f"Error calculating stats: {e}")
            import traceback
            traceback.print_exc()
            return 0, 0


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
