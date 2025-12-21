"""
Minimal Game Overlay for Pokemon TCG Live Monitor v2.0
Ultra-compact, professional overlay that follows the game and allows click-through
"""

VERSION = "2.0"

import sys
import os
import win32gui
import win32process
import psutil
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor
from BattleDatabase import BattleDatabase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "Logs")


def create_pokeball_icon(ball_type="poke"):
    """Create 8-bit style pokeball icons for different leagues"""
    # 12x12 pixel pokeball
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # Keep it pixelated
    
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
        self.last_log_count = 0
        self.game_hwnd = None
        self.current_rank = "--"
        self.max_rank = "--"
        self.wins = 0
        self.losses = 0
        self.parent_monitor_running = True
        self.db = BattleDatabase()  # Initialize database connection
        
        self.init_ui()
        self.load_stats()
        
        # Auto-refresh stats every 3 seconds
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.load_stats)
        self.refresh_timer.start(3000)
        
        # Check game window position every second
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self.follow_game_window)
        self.position_timer.start(1000)
        
        # Check if parent monitor is still running every 2 seconds
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.check_monitor_running)
        self.monitor_timer.start(2000)
    
    def check_monitor_running(self):
        """Check if TCGLiveMonitor.py is still running, exit if not"""
        try:
            monitor_running = False
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline')
                    if cmdline and 'python' in proc.info['name'].lower():
                        # Check if this process is running TCGLiveMonitor.py
                        cmdline_str = ' '.join(cmdline).lower()
                        if 'tcglivemonitor.py' in cmdline_str:
                            monitor_running = True
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if not monitor_running and self.parent_monitor_running:
                print("Monitor closed, shutting down overlay...")
                QApplication.quit()
            
            self.parent_monitor_running = monitor_running
        except Exception as e:
            print(f"Error checking monitor: {e}")
    
    def find_game_window(self):
        """Find Pokemon TCG Live window"""
        def callback(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if "Pokémon TCG Live" in title or "Pokemon TCG Live" in title:
                    hwnds.append(hwnd)
            return True
        
        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        return hwnds[0] if hwnds else None
    
    def follow_game_window(self):
        """Position overlay relative to game window"""
        hwnd = self.find_game_window()
        if not hwnd:
            # Game not found, hide overlay
            if self.isVisible():
                self.hide()
            return
        
        self.game_hwnd = hwnd
        
        try:
            rect = win32gui.GetWindowRect(hwnd)
            game_x, game_y, game_right, game_bottom = rect
            
            # Position in bottom-right corner of game window, offset inward
            margin = 10
            x = game_right - self.width() - margin
            y = game_bottom - self.height() - margin
            
            self.move(x, y)
            
            # Always show when game is found
            if not self.isVisible():
                self.show()
        except:
            pass
    
    def init_ui(self):
        """Initialize minimal UI"""
        # Window properties - CLICK-THROUGH and always on top
        self.setWindowTitle("TCG Monitor")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput  # Click-through!
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
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
        
        layout.addLayout(stats_layout)
        
        # Apply minimal styling
        self.apply_style()
        
        # Very small initial size (slightly wider for icon)
        self.setFixedSize(156, 24)
    
    def apply_style(self):
        """Apply minimal, professional styling"""
        self.setStyleSheet("""
            QFrame#container {
                background-color: rgba(20, 20, 20, 220);
                border: 1px solid rgba(80, 80, 80, 180);
                border-radius: 4px;
            }
            QLabel#stats {
                color: rgba(220, 220, 220, 255);
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
                font-weight: 500;
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
            print(f"Error loading stats: {e}")
            import traceback
            traceback.print_exc()
    
    def update_display(self):
        """Update the stats label and pokeball icon"""
        # Update text
        self.stats_label.setText(
            f"Elo:{self.current_rank} | Max:{self.max_rank} | {self.wins}-{self.losses}"
        )
        
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
