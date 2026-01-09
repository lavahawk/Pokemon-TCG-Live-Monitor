"""
Stats Dashboard for Pokemon TCG Live Monitor v2.1
Modern, sleek UI with transparent glass-morphism design
"""

VERSION = "2.1"

import sys
import os
import webbrowser
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QFrame, QPushButton, QScrollArea, QGridLayout, QGraphicsOpacityEffect,
    QTabWidget, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QLinearGradient, QFont
from BattleDatabase import BattleDatabase

try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available, graphs will not display")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class MplCanvas(FigureCanvasQTAgg):
    """Matplotlib canvas with modern dark theme"""
    def __init__(self, parent=None, width=5, height=3, dpi=100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        self.figure.patch.set_facecolor('none')
        self.figure.patch.set_alpha(0.0)
        
        self.axes = self.figure.add_subplot(111)
        
        # Modern dark styling
        self.axes.set_facecolor('#0a0a0a')
        self.axes.patch.set_alpha(0.3)
        
        # Remove top and right spines for cleaner look
        self.axes.spines['top'].set_visible(False)
        self.axes.spines['right'].set_visible(False)
        self.axes.spines['bottom'].set_color('#2a2a2a')
        self.axes.spines['left'].set_color('#2a2a2a')
        self.axes.spines['bottom'].set_linewidth(0.5)
        self.axes.spines['left'].set_linewidth(0.5)
        
        super(MplCanvas, self).__init__(self.figure)
        self.setStyleSheet("background-color: transparent;")
        self.setMinimumSize(300, 200)


class StatsWindow(QWidget):
    """Modern sleek stats dashboard - minimizes to mini overlay"""
    
    def __init__(self, parent_overlay=None):
        super().__init__()
        self.db = BattleDatabase()
        self.parent_overlay = parent_overlay
        self.is_minimized = False
        self.console_hidden = False  # Track console visibility state
        self.monitor_console_hwnd = None  # Handle to monitor's console window
        
        # For dragging
        self.dragging = False
        self.drag_position = None
        
        self.init_ui()
        self.load_stats()
        
        # Auto-refresh every 10 seconds
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.load_stats)
        self.refresh_timer.start(10000)
    
    def init_ui(self):
        """Initialize modern UI with glass-morphism design"""
        # Window properties - transparent, frameless, always on top
        self.setWindowTitle("TCG Stats")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Main container with glass effect
        self.container = QFrame()
        self.container.setObjectName("glassContainer")
        
        # Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)
        
        # Container layout
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        
        # Title bar
        title_bar = self.create_title_bar()
        layout.addWidget(title_bar)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("mainTabs")
        
        # Stats Tab
        stats_tab = self.create_stats_tab()
        self.tab_widget.addTab(stats_tab, "Stats")
        
        # Settings Tab
        settings_tab = self.create_settings_tab()
        self.tab_widget.addTab(settings_tab, "Advanced")
        
        # Donate Tab
        support_tab = self.create_support_tab()
        self.tab_widget.addTab(support_tab, "Donate")
        
        layout.addWidget(self.tab_widget)
        
        # Apply modern styling
        self.apply_modern_style()
        
        # Set size
        self.setFixedSize(750, 650)
    
    def create_title_bar(self):
        """Create modern title bar with minimize/close"""
        title_bar = QFrame()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(32)  # Smaller title bar
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(12)
        
        # Empty title area - clean minimal design
        layout.addStretch()
        
        # Minimize button (down arrow) - only button needed
        min_btn = QPushButton("▼")
        min_btn.setObjectName("minBtn")
        min_btn.setFixedSize(22, 22)  # Slightly smaller
        min_btn.clicked.connect(self.minimize_to_overlay)
        min_btn.setToolTip("Minimize to overlay")
        layout.addWidget(min_btn)
        
        return title_bar
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking on title bar area (top 32px)
            if event.position().y() < 32:
                self.dragging = True
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging"""
        if self.dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            event.accept()
    
    def minimize_to_overlay(self):
        """Minimize stats window back to mini overlay"""
        self.is_minimized = True
        self.hide()
        if self.parent_overlay:
            self.parent_overlay.arrow_label.setText("▲")  # Flip arrow back up
            self.parent_overlay.stats_window = None
    
    def create_stats_tab(self):
        """Create stats tab with all statistics"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setObjectName("scrollArea")
        
        content_widget = QWidget()
        content_widget.setObjectName("contentWidget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(12, 8, 12, 20)  # Added bottom padding
        
        # Stats cards
        self.stats_summary = self.create_stats_cards()
        content_layout.addWidget(self.stats_summary)
        
        # Graphs section
        if MATPLOTLIB_AVAILABLE:
            graphs_container = self.create_graphs_section()
            content_layout.addWidget(graphs_container)
        
        # Deck usage section
        self.deck_usage_widget = self.create_deck_section()
        content_layout.addWidget(self.deck_usage_widget)
        
        # Recent battles
        self.recent_battles_widget = self.create_battles_section()
        content_layout.addWidget(self.recent_battles_widget)
        
        # Limitless integration
        limitless_section = self.create_limitless_section()
        content_layout.addWidget(limitless_section)
        
        content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        return scroll
    
    def create_settings_tab(self):
        """Create settings/advanced tab with debug controls"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("scrollArea")
        
        content = QWidget()
        content.setObjectName("contentWidget")
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Debugging Section
        debug_card = self.create_card("Debugging & Development")
        debug_layout = QVBoxLayout()
        debug_layout.setSpacing(8)
        debug_layout.setContentsMargins(12, 8, 12, 12)
        
        # Hide/Show Console button
        self.console_btn = QPushButton("Hide Console Window")
        self.console_btn.setObjectName("settingsBtn")
        self.console_btn.setFixedHeight(40)
        self.console_btn.clicked.connect(self.toggle_console)
        debug_layout.addWidget(self.console_btn)
        
        # Check console availability on startup
        self.check_console_availability()
        
        # OCR Test Window button
        ocr_test_btn = QPushButton("Open OCR Test Window")
        ocr_test_btn.setObjectName("settingsBtn")
        ocr_test_btn.setFixedHeight(40)
        ocr_test_btn.clicked.connect(self.launch_ocr_test)
        debug_layout.addWidget(ocr_test_btn)
        
        # Run AI Parse button
        ai_parse_btn = QPushButton("Run AI Battle Log Parser")
        ai_parse_btn.setObjectName("settingsBtn")
        ai_parse_btn.setFixedHeight(40)
        ai_parse_btn.clicked.connect(self.launch_ai_parser)
        debug_layout.addWidget(ai_parse_btn)
        
        desc = QLabel("Quick access to development tools and debugging features")
        desc.setObjectName("settingsDesc")
        desc.setWordWrap(True)
        debug_layout.addWidget(desc)
        
        debug_card.layout().addLayout(debug_layout)
        layout.addWidget(debug_card)
        
        # AutoRun Section
        autorun_card = self.create_card("AutoRun Configuration")
        autorun_layout = QVBoxLayout()
        autorun_layout.setSpacing(8)
        autorun_layout.setContentsMargins(12, 8, 12, 12)
        
        add_autorun_btn = QPushButton("Add to Windows Startup")
        add_autorun_btn.setObjectName("settingsBtn")
        add_autorun_btn.setFixedHeight(40)
        add_autorun_btn.clicked.connect(self.add_autorun)
        autorun_layout.addWidget(add_autorun_btn)
        
        remove_autorun_btn = QPushButton("Remove from Windows Startup")
        remove_autorun_btn.setObjectName("settingsBtn")
        remove_autorun_btn.setFixedHeight(40)
        remove_autorun_btn.clicked.connect(self.remove_autorun)
        autorun_layout.addWidget(remove_autorun_btn)
        
        autorun_desc = QLabel("Configure the monitor to automatically start with Windows")
        autorun_desc.setObjectName("settingsDesc")
        autorun_desc.setWordWrap(True)
        autorun_layout.addWidget(autorun_desc)
        
        autorun_card.layout().addLayout(autorun_layout)
        layout.addWidget(autorun_card)
        
        # Battle Management Section
        battle_mgmt_card = self.create_card("Battle Database Management")
        battle_mgmt_layout = QVBoxLayout()
        battle_mgmt_layout.setSpacing(8)
        battle_mgmt_layout.setContentsMargins(12, 8, 12, 12)
        
        # Recent battles list
        battles_label = QLabel("Recent Battles (Last 20)")
        battles_label.setStyleSheet("color: rgba(255, 255, 255, 0.8); font-size: 11px; font-weight: 600; margin-top: 4px;")
        battle_mgmt_layout.addWidget(battles_label)
        
        # Scrollable list of battles
        self.battle_mgmt_scroll = QScrollArea()
        self.battle_mgmt_scroll.setWidgetResizable(True)
        self.battle_mgmt_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.battle_mgmt_scroll.setFixedHeight(300)
        self.battle_mgmt_scroll.setStyleSheet("""
            QScrollArea {
                background-color: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
            QScrollBar:vertical {
                background-color: rgba(255, 255, 255, 0.05);
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(255, 255, 255, 0.2);
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: rgba(255, 255, 255, 0.3);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self.battle_mgmt_content = QWidget()
        self.battle_mgmt_content.setStyleSheet("background-color: transparent;")
        self.battle_mgmt_list_layout = QVBoxLayout(self.battle_mgmt_content)
        self.battle_mgmt_list_layout.setSpacing(4)
        self.battle_mgmt_list_layout.setContentsMargins(8, 8, 8, 8)
        
        self.battle_mgmt_scroll.setWidget(self.battle_mgmt_content)
        battle_mgmt_layout.addWidget(self.battle_mgmt_scroll)
        
        # Refresh button
        refresh_battles_btn = QPushButton("Refresh Battle List")
        refresh_battles_btn.setObjectName("settingsBtn")
        refresh_battles_btn.setFixedHeight(35)
        refresh_battles_btn.clicked.connect(self.refresh_battle_management)
        battle_mgmt_layout.addWidget(refresh_battles_btn)
        
        battle_mgmt_desc = QLabel("View and delete recent battles. Use this to remove duplicates or incorrect entries.")
        battle_mgmt_desc.setObjectName("settingsDesc")
        battle_mgmt_desc.setWordWrap(True)
        battle_mgmt_layout.addWidget(battle_mgmt_desc)
        
        battle_mgmt_card.layout().addLayout(battle_mgmt_layout)
        layout.addWidget(battle_mgmt_card)
        
        # Load initial battles
        self.refresh_battle_management()
        
        # Application Control Section
        app_control_card = self.create_card("Application Control")
        app_control_layout = QVBoxLayout()
        app_control_layout.setSpacing(8)
        app_control_layout.setContentsMargins(12, 8, 12, 12)
        
        # Close Application button
        close_app_btn = QPushButton("Close Application")
        close_app_btn.setObjectName("closeAppBtn")
        close_app_btn.setFixedHeight(45)
        close_app_btn.setStyleSheet("""
            QPushButton#closeAppBtn {
                background-color: rgba(239, 83, 80, 0.15);
                color: #EF5350;
                border: 1px solid rgba(239, 83, 80, 0.3);
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#closeAppBtn:hover {
                background-color: rgba(239, 83, 80, 0.25);
                border: 1px solid rgba(239, 83, 80, 0.5);
            }
            QPushButton#closeAppBtn:pressed {
                background-color: rgba(239, 83, 80, 0.35);
            }
        """)
        close_app_btn.clicked.connect(self.close_application)
        app_control_layout.addWidget(close_app_btn)
        
        app_control_desc = QLabel("Completely close the Stats Dashboard and Overlay")
        app_control_desc.setObjectName("settingsDesc")
        app_control_desc.setWordWrap(True)
        app_control_layout.addWidget(app_control_desc)
        
        app_control_card.layout().addLayout(app_control_layout)
        layout.addWidget(app_control_card)
        
        layout.addStretch()
        
        scroll.setWidget(content)
        return scroll
    
    def create_support_tab(self):
        """Create support tab with Buy Me a Coffee"""
        content = QWidget()
        content.setObjectName("contentWidget")
        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        layout.setContentsMargins(12, 12, 12, 12)
        
        layout.addStretch()
        
        # Support header
        header = QLabel("Support Development")
        header.setStyleSheet("color: rgba(255, 255, 255, 0.95); font-size: 24px; font-weight: 600;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Description
        desc = QLabel("If you enjoy using this tool and want to support its development,\nconsider buying me a coffee! ☕")
        desc.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-size: 13px; line-height: 1.5;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Buy Me a Coffee button
        coffee_btn = QPushButton("Buy Me a Coffee")
        coffee_btn.setObjectName("coffeeBtn")
        coffee_btn.setFixedHeight(50)
        coffee_btn.setFixedWidth(250)
        coffee_btn.clicked.connect(lambda: webbrowser.open("https://www.buymeacoffee.com/lavahawk"))
        layout.addWidget(coffee_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Thank you message
        thanks = QLabel("Thank you for your support! 💙")
        thanks.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 12px; font-style: italic;")
        thanks.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(thanks)
        
        layout.addStretch()
        
        return content
    
    def create_card(self, title):
        """Create a styled card container"""
        card = QFrame()
        card.setObjectName("settingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(0)
        card_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QLabel(title)
        header.setStyleSheet("color: rgba(255, 255, 255, 0.9); font-size: 14px; font-weight: 600; padding: 12px;")
        card_layout.addWidget(header)
        
        return card
    
    def check_console_availability(self):
        """Check if console window is available and set button state"""
        try:
            import ctypes
            import win32gui
            import win32process
            import psutil
            
            print("\n[Console Detection] Starting...")
            print(f"[Console Detection] Current process PID: {os.getpid()}")
            
            console_found = False
            monitor_pid = None
            
            # Method 1: Try PID file first
            pid_file = os.path.join(BASE_DIR, ".monitor_pid")
            print(f"[Console Detection] Checking PID file: {pid_file}")
            
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        file_pid = int(f.read().strip())
                    
                    print(f"[Console Detection] PID from file: {file_pid}")
                    
                    # Verify process is still running
                    try:
                        process = psutil.Process(file_pid)
                        # Check if it's actually TCGLiveMonitor (not Stats UI or other script)
                        if 'python' in process.name().lower():
                            cmdline = ' '.join(process.cmdline())
                            if 'TCGLiveMonitor.py' in cmdline and file_pid != os.getpid():
                                monitor_pid = file_pid
                                print(f"[Console Detection] ✓ Valid monitor PID from file: {monitor_pid}")
                            else:
                                print(f"[Console Detection] PID {file_pid} is not TCGLiveMonitor (cmdline: {cmdline})")
                    except psutil.NoSuchProcess:
                        print(f"[Console Detection] PID {file_pid} from file is stale")
                except Exception as e:
                    print(f"[Console Detection] Error reading PID file: {e}")
            
            # Method 2: Search all Python processes for TCGLiveMonitor
            if monitor_pid is None:
                print("[Console Detection] Searching for TCGLiveMonitor process...")
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        # Skip our own process
                        if proc.info['pid'] == os.getpid():
                            continue
                            
                        if 'python' in proc.info['name'].lower():
                            cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                            if 'TCGLiveMonitor.py' in cmdline:
                                monitor_pid = proc.info['pid']
                                print(f"[Console Detection] ✓ Found TCGLiveMonitor: PID {monitor_pid}")
                                print(f"[Console Detection]   Command: {cmdline}")
                                # Update PID file with correct PID
                                try:
                                    with open(pid_file, 'w') as f:
                                        f.write(str(monitor_pid))
                                    print(f"[Console Detection] Updated PID file")
                                except:
                                    pass
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            
            # Method 3: Find console window for the monitor process (NOT our own)
            if monitor_pid:
                print(f"[Console Detection] Looking for console window (Monitor PID: {monitor_pid}, Our PID: {os.getpid()})...")
                
                def find_console_callback(hwnd, lParam):
                    try:
                        if win32gui.IsWindowVisible(hwnd):
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            # ONLY match the monitor's console, not ours
                            if pid == monitor_pid:
                                class_name = win32gui.GetClassName(hwnd)
                                title = win32gui.GetWindowText(hwnd)
                                if class_name == "ConsoleWindowClass":
                                    self.monitor_console_hwnd = hwnd
                                    print(f"[Console Detection] ✓ FOUND MONITOR CONSOLE")
                                    print(f"[Console Detection]   PID: {pid}, HWND: {hwnd}, Title: '{title}'")
                                    return False
                    except:
                        pass
                    return True
                
                self.monitor_console_hwnd = None
                win32gui.EnumWindows(find_console_callback, None)
                
                if self.monitor_console_hwnd:
                    console_found = True
                    print(f"[Console Detection] ✓ Console ready for control")
                else:
                    print(f"[Console Detection] ✗ No console window found for monitor PID {monitor_pid}")
            else:
                print("[Console Detection] ✗ TCGLiveMonitor process not found")
            
            # Do NOT use fallback to own console - we only want the monitor's console
            if not console_found:
                self.console_btn.setText("No Console Available")
                self.console_btn.setEnabled(False)
                self.console_hidden = False
                self.monitor_console_hwnd = None
                print("[Console Detection] ✗ Monitor console not found")
            else:
                # Check saved preference and apply it
                self.load_console_preference()
                
        except Exception as e:
            print(f"[Console Detection] Error: {e}")
            import traceback
            traceback.print_exc()
    
    def load_console_preference(self):
        """Load and apply saved console visibility preference"""
        try:
            pref_file = os.path.join(BASE_DIR, ".console_pref")
            if os.path.exists(pref_file):
                with open(pref_file, 'r') as f:
                    pref = f.read().strip()
                
                if pref == "hidden":
                    print("[Console Pref] Applying saved preference: hidden")
                    # Hide console immediately
                    import ctypes
                    if self.monitor_console_hwnd:
                        ctypes.windll.user32.ShowWindow(self.monitor_console_hwnd, 0)
                        self.console_hidden = True
                        self.console_btn.setText("Show Console Window")
                        print("✓ Console auto-hidden on startup")
                else:
                    print("[Console Pref] Applying saved preference: visible")
                    self.console_hidden = False
                    self.console_btn.setText("Hide Console Window")
            else:
                print("[Console Pref] No saved preference, defaulting to visible")
                self.console_btn.setText("Hide Console Window")
        except Exception as e:
            print(f"[Console Pref] Error loading preference: {e}")
    
    def save_console_preference(self):
        """Save console visibility preference"""
        try:
            pref_file = os.path.join(BASE_DIR, ".console_pref")
            with open(pref_file, 'w') as f:
                f.write("hidden" if self.console_hidden else "visible")
            print(f"[Console Pref] Saved: {'hidden' if self.console_hidden else 'visible'}")
        except Exception as e:
            print(f"[Console Pref] Error saving preference: {e}")
    
    def toggle_console(self):
        """Toggle console window visibility"""
        try:
            import ctypes
            
            # Check if we have a console window handle
            if not hasattr(self, 'monitor_console_hwnd') or self.monitor_console_hwnd is None:
                print("No console window available to toggle")
                return
            
            hwnd = self.monitor_console_hwnd
            
            # Toggle based on current state
            if self.console_hidden:
                # Show console
                ctypes.windll.user32.ShowWindow(hwnd, 1)  # SW_SHOWNORMAL
                self.console_hidden = False
                self.console_btn.setText("Hide Console Window")
                print("✓ Monitor console window shown")
            else:
                # Hide console
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
                self.console_hidden = True
                self.console_btn.setText("Show Console Window")
                print("✓ Monitor console window hidden (running headless)")
            
            # Save preference
            self.save_console_preference()
                
        except Exception as e:
            print(f"Error toggling console: {e}")
            import traceback
            traceback.print_exc()
    
    def launch_ocr_test(self):
        """Launch OCR test window"""
        import subprocess
        try:
            # Run the main script which will show the OCR test window
            subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "TCGLiveMonitor.py"), "--ocr-test"],
                           creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            print(f"Error launching OCR test: {e}")
    
    def launch_ai_parser(self):
        """Launch AI battle log parser"""
        import subprocess
        try:
            subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "AIParseBattleLog.py")],
                           creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            print(f"Error launching AI parser: {e}")
    
    def add_autorun(self):
        """Add to Windows startup"""
        import subprocess
        print("\n" + "="*50)
        print("Adding TCG Live Monitor to Windows Startupb via task scheduler...")
        print("="*50)
        try:
            result = subprocess.run([sys.executable, os.path.join(BASE_DIR, "AutoRun_Add.py")], 
                                  check=True, 
                                  capture_output=True, 
                                  text=True)
            print(result.stdout)
            print("\n✅ Successfully added to Windows startup!")
            print("   The monitor will now start automatically when you log in.")
            print("="*50 + "\n")
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Error adding to startup:")
            print(f"   {e.stderr}")
            print("="*50 + "\n")
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            print("="*50 + "\n")
    
    def remove_autorun(self):
        """Remove from Windows startup"""
        import subprocess
        print("\n" + "="*50)
        print("🔧 Removing TCG Live Monitor from Windows Startup...")
        print("="*50)
        try:
            result = subprocess.run([sys.executable, os.path.join(BASE_DIR, "AutoRun_Remove.py")], 
                                  check=True, 
                                  capture_output=True, 
                                  text=True)
            print(result.stdout)
            print("\n✅ Successfully removed from Windows startup!")
            print("   The monitor will no longer start automatically.")
            print("="*50 + "\n")
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Error removing from startup:")
            print(f"   {e.stderr}")
            print("="*50 + "\n")
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            print("="*50 + "\n")
    
    def close_application(self):
        """Close the entire application including overlay and monitor process"""
        try:
            # Confirm closure
            reply = QMessageBox.question(
                self, 
                'Close Application',
                'Are you sure you want to close the entire TCG Live Monitor?\n\nThis will stop all monitoring and close all windows.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                print("\n" + "="*50)
                print("Closing TCG Live Monitor...")
                print("="*50 + "\n")
                
                # Try to terminate the monitor process
                try:
                    import psutil
                    pid_file = os.path.join(BASE_DIR, ".monitor_pid")
                    if os.path.exists(pid_file):
                        with open(pid_file, 'r') as f:
                            monitor_pid = int(f.read().strip())
                        
                        # Kill the monitor process
                        try:
                            process = psutil.Process(monitor_pid)
                            process.terminate()
                            process.wait(timeout=3)
                            print(f"✓ Terminated monitor process (PID: {monitor_pid})")
                        except psutil.NoSuchProcess:
                            print("Monitor process already terminated")
                        except psutil.TimeoutExpired:
                            process.kill()
                            print(f"✓ Force killed monitor process (PID: {monitor_pid})")
                        
                        # Clean up PID file
                        os.remove(pid_file)
                except Exception as e:
                    print(f"Warning: Could not terminate monitor process: {e}")
                
                # Close overlay if it exists
                if hasattr(self, 'parent_overlay') and self.parent_overlay:
                    self.parent_overlay.close()
                
                # Close this window
                self.close()
                
                # Quit the application
                QApplication.quit()
                
        except Exception as e:
            print(f"Error closing application: {e}")
            import traceback
            traceback.print_exc()
    
    def create_stats_cards(self):
        """Create modern stat cards grid"""
        container = QFrame()
        container.setObjectName("statsGrid")
        
        layout = QGridLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Stat cards data
        self.total_games_label = QLabel("--")
        self.win_rate_label = QLabel("--%")
        self.current_elo_label = QLabel("--")
        self.best_elo_label = QLabel("--")
        self.total_wins_label = QLabel("--")
        self.total_losses_label = QLabel("--")
        
        cards = [
            ("TOTAL GAMES", self.total_games_label, "#4A9FD8"),
            ("WIN RATE", self.win_rate_label, "#9CC344"),
            ("CURRENT ELO", self.current_elo_label, "#F9A825"),
            ("BEST ELO", self.best_elo_label, "#7B1FA2"),
            ("WINS", self.total_wins_label, "#66BB6A"),
            ("LOSSES", self.total_losses_label, "#EF5350"),
        ]
        
        row, col = 0, 0
        for label_text, value_label, color in cards:
            card = self.create_stat_card(label_text, value_label, color)
            layout.addWidget(card, row, col)
            
            col += 1
            if col >= 3:
                col = 0
                row += 1
        
        return container
    
    def create_stat_card(self, title, value_label, accent_color):
        """Create individual modern stat card"""
        card = QFrame()
        card.setObjectName("statCard")
        card.setStyleSheet(f"""
            QFrame#statCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 0.03),
                    stop:1 rgba(255, 255, 255, 0.01));
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                border-left: 3px solid {accent_color};
            }}
        """)
        card.setFixedHeight(85)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        
        # Title
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        title_label.setStyleSheet(f"color: {accent_color}; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(title_label)
        
        # Value
        value_label.setObjectName("cardValue")
        value_label.setStyleSheet("color: rgba(255, 255, 255, 0.95); font-size: 28px; font-weight: 700;")
        layout.addWidget(value_label)
        
        layout.addStretch()
        
        return card
    
    def create_graphs_section(self):
        """Create modern graphs section"""
        container = QFrame()
        container.setObjectName("graphsContainer")
        
        layout = QHBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Elo graph
        self.elo_canvas = MplCanvas(self, width=4.5, height=2.8, dpi=90)
        elo_frame = self.create_graph_card("ELO PROGRESSION", self.elo_canvas)
        layout.addWidget(elo_frame)
        
        # Win rate graph
        self.winrate_canvas = MplCanvas(self, width=4.5, height=2.8, dpi=90)
        winrate_frame = self.create_graph_card("WIN RATE TREND", self.winrate_canvas)
        layout.addWidget(winrate_frame)
        
        return container
    
    def create_graph_card(self, title, canvas):
        """Create modern graph card"""
        card = QFrame()
        card.setObjectName("graphCard")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Title
        title_label = QLabel(title)
        title_label.setObjectName("graphTitle")
        layout.addWidget(title_label)
        
        # Canvas
        layout.addWidget(canvas)
        
        return card
    
    def create_deck_section(self):
        """Create modern deck usage section"""
        card = QFrame()
        card.setObjectName("deckCard")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # Header
        header = QLabel("DECK USAGE")
        header.setObjectName("sectionHeader")
        layout.addWidget(header)
        
        # Deck list
        self.deck_list_layout = QVBoxLayout()
        self.deck_list_layout.setSpacing(6)
        layout.addLayout(self.deck_list_layout)
        
        return card
    
    def create_battles_section(self):
        """Create modern battles section"""
        card = QFrame()
        card.setObjectName("battlesCard")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # Header
        header = QLabel("RECENT BATTLES")
        header.setObjectName("sectionHeader")
        layout.addWidget(header)
        
        # Battles list
        self.battles_list_layout = QVBoxLayout()
        self.battles_list_layout.setSpacing(4)
        layout.addLayout(self.battles_list_layout)
        
        return card
    
    def create_limitless_section(self):
        """Create Limitless integration section"""
        card = QFrame()
        card.setObjectName("limitlessCard")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # Header
        header = QLabel("LIMITLESS TCG")
        header.setObjectName("sectionHeader")
        layout.addWidget(header)
        
        # Button
        btn = QPushButton("Open Limitless TCG")
        btn.setObjectName("limitlessBtn")
        btn.setFixedHeight(36)
        btn.clicked.connect(self.open_limitless)
        layout.addWidget(btn)
        
        # Placeholder
        placeholder = QLabel("Chat relay feature coming soon")
        placeholder.setObjectName("placeholder")
        layout.addWidget(placeholder)
        
        return card
    
    def open_limitless(self):
        """Open Limitless TCG website"""
        webbrowser.open("https://play.limitlesstcg.com/")
    
    def load_stats(self):
        """Load and display all statistics"""
        try:
            # Get overall stats
            total, wins, losses, best_elo, worst_elo = self.db.get_all_time_stats()
            current_elo = self.db.get_current_rank()
            
            self.total_games_label.setText(str(total))
            self.total_wins_label.setText(str(wins))
            self.total_losses_label.setText(str(losses))
            
            if total > 0:
                win_rate = (wins / total) * 100
                self.win_rate_label.setText(f"{win_rate:.1f}%")
            else:
                self.win_rate_label.setText("0%")
            
            self.current_elo_label.setText(str(current_elo) if current_elo else "--")
            self.best_elo_label.setText(str(best_elo) if best_elo else "--")
            
            # Load graphs
            if MATPLOTLIB_AVAILABLE:
                try:
                    self.update_elo_graph()
                    self.update_winrate_graph()
                except Exception as graph_error:
                    print(f"Graph error: {graph_error}")
                    import traceback
                    traceback.print_exc()
            else:
                print("Warning: matplotlib not available - graphs disabled")
            
            # Load deck usage
            self.update_deck_usage()
            
            # Load recent battles
            self.update_recent_battles()
            
        except Exception as e:
            print(f"Error loading stats: {e}")
            import traceback
            traceback.print_exc()
    
    def update_elo_graph(self):
        """Update Elo progression graph"""
        try:
            data = self.db.get_elo_history(limit=50)
            if not data:
                return
            
            # Parse timestamps and elos
            times = []
            elos = []
            for row in data:
                try:
                    times.append(datetime.fromisoformat(row[0]))
                    elos.append(int(row[1]))
                except:
                    continue
            
            if not times or not elos:
                return
            
            # Clear previous plot
            self.elo_canvas.axes.cla()
            
            # Set dark transparent background  
            self.elo_canvas.axes.set_facecolor((0.04, 0.04, 0.04, 0.3))
            self.elo_canvas.figure.patch.set_facecolor('none')
            self.elo_canvas.figure.patch.set_alpha(0)
            
            # Plot the main line
            self.elo_canvas.axes.plot(times, elos, 
                                     color='#4A9FD8', 
                                     linewidth=2.5,
                                     marker='o',
                                     markersize=5,
                                     markerfacecolor='#6BB6E8',
                                     markeredgecolor='#4A9FD8',
                                     markeredgewidth=1.5)
            
            # Fill area under curve
            self.elo_canvas.axes.fill_between(times, elos, 
                                             min(elos) - 10,
                                             alpha=0.2,
                                             color='#4A9FD8')
            
            # Set y limits with padding
            y_range = max(elos) - min(elos)
            padding = max(10, y_range * 0.15)
            self.elo_canvas.axes.set_ylim(min(elos) - padding, max(elos) + padding)
            
            # Style the axes
            self.elo_canvas.axes.tick_params(colors='#666666', labelsize=8)
            self.elo_canvas.axes.grid(True, alpha=0.1, color='#444444', linewidth=0.5)
            
            # Remove spines
            self.elo_canvas.axes.spines['top'].set_visible(False)
            self.elo_canvas.axes.spines['right'].set_visible(False)
            self.elo_canvas.axes.spines['bottom'].set_color('#2a2a2a')
            self.elo_canvas.axes.spines['left'].set_color('#2a2a2a')
            self.elo_canvas.axes.spines['bottom'].set_linewidth(0.5)
            self.elo_canvas.axes.spines['left'].set_linewidth(0.5)
            
            # Smart date formatting based on time range
            time_range = (times[-1] - times[0]).total_seconds()
            if time_range < 3600:  # Less than 1 hour
                date_format = '%H:%M'
            elif time_range < 86400:  # Less than 1 day
                date_format = '%H:%M'
            elif time_range < 604800:  # Less than 1 week
                date_format = '%m/%d %H:%M'
            else:  # 1 week or more
                date_format = '%m/%d'
            
            # Select evenly spaced tick positions (max 4-5 ticks for better spacing)
            num_points = len(times)
            if num_points <= 4:
                tick_indices = range(num_points)
            else:
                # Always include first and last, space out the rest
                step = max(1, num_points // 4)
                tick_indices = list(range(0, num_points, step))
                # Always include the last point
                if tick_indices[-1] != num_points - 1:
                    tick_indices.append(num_points - 1)
            
            # Format x-axis labels for selected ticks only
            tick_positions = [times[i] for i in tick_indices]
            tick_labels = [times[i].strftime(date_format) for i in tick_indices]
            
            self.elo_canvas.axes.set_xticks(tick_positions)
            self.elo_canvas.axes.set_xticklabels(tick_labels, rotation=35, ha='right', fontsize=8)
            
            # Manual positioning with more bottom space for rotated labels
            self.elo_canvas.figure.subplots_adjust(left=0.15, right=0.95, top=0.95, bottom=0.25)
            
            # Redraw
            self.elo_canvas.draw()
            
        except Exception as e:
            print(f"Error in Elo graph: {e}")
            import traceback
            traceback.print_exc()
    
    def update_winrate_graph(self):
        """Update win rate graph"""
        try:
            data = self.db.get_win_rate_over_time(days=30)
            if not data:
                return
            
            # Parse dates and win rates
            dates = []
            win_rates = []
            for row in data:
                try:
                    dates.append(datetime.strptime(row[0], '%Y-%m-%d'))
                    wr = (row[1] / row[3]) * 100 if row[3] > 0 else 0
                    win_rates.append(wr)
                except:
                    continue
            
            if not dates or not win_rates:
                return
            
            # Clear previous plot
            self.winrate_canvas.axes.cla()
            
            # Set dark transparent background
            self.winrate_canvas.axes.set_facecolor((0.04, 0.04, 0.04, 0.3))
            self.winrate_canvas.figure.patch.set_facecolor('none')
            self.winrate_canvas.figure.patch.set_alpha(0)
            
            # Plot the main line
            self.winrate_canvas.axes.plot(dates, win_rates,
                                         color='#9CC344',
                                         linewidth=2.5,
                                         marker='s',
                                         markersize=5,
                                         markerfacecolor='#B4D96A',
                                         markeredgecolor='#9CC344',
                                         markeredgewidth=1.5)
            
            # Fill area under curve
            self.winrate_canvas.axes.fill_between(dates, win_rates, 0,
                                                  alpha=0.2,
                                                  color='#9CC344')
            
            # Add 50% reference line
            self.winrate_canvas.axes.axhline(y=50,
                                            color='#666666',
                                            linestyle='--',
                                            linewidth=1,
                                            alpha=0.4)
            
            # Set y limits
            self.winrate_canvas.axes.set_ylim(0, 105)
            
            # Style the axes
            self.winrate_canvas.axes.tick_params(colors='#666666', labelsize=8)
            self.winrate_canvas.axes.grid(True, alpha=0.1, color='#444444', linewidth=0.5)
            
            # Remove spines
            self.winrate_canvas.axes.spines['top'].set_visible(False)
            self.winrate_canvas.axes.spines['right'].set_visible(False)
            self.winrate_canvas.axes.spines['bottom'].set_color('#2a2a2a')
            self.winrate_canvas.axes.spines['left'].set_color('#2a2a2a')
            self.winrate_canvas.axes.spines['bottom'].set_linewidth(0.5)
            self.winrate_canvas.axes.spines['left'].set_linewidth(0.5)
            
            # Smart date formatting based on date range
            date_range = (dates[-1] - dates[0]).days
            if date_range <= 7:  # 1 week or less
                date_format = '%m/%d'
            elif date_range <= 30:  # 1 month or less
                date_format = '%m/%d'
            else:  # More than 1 month
                date_format = '%m/%d'
            
            # Format x-axis labels
            formatted_labels = []
            for d in dates:
                formatted_labels.append(d.strftime(date_format))
            
            self.winrate_canvas.axes.set_xticks(dates)
            self.winrate_canvas.axes.set_xticklabels(formatted_labels, rotation=45, ha='right')
            
            # Manual positioning
            self.winrate_canvas.figure.subplots_adjust(left=0.15, right=0.95, top=0.95, bottom=0.2)
            
            # Redraw
            self.winrate_canvas.draw()
            
        except Exception as e:
            print(f"Error in win rate graph: {e}")
            import traceback
            traceback.print_exc()
    
    def update_deck_usage(self):
        """Update deck usage with modern horizontal bars"""
        try:
            # Clear existing
            while self.deck_list_layout.count():
                child = self.deck_list_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            decks = self.db.get_deck_usage_stats()
            
            if not decks:
                no_data = QLabel("No deck data yet")
                no_data.setObjectName("noData")
                no_data.setStyleSheet("color: rgba(255, 255, 255, 0.3); font-size: 11px; font-style: italic;")
                self.deck_list_layout.addWidget(no_data)
                return
            
            max_games = decks[0][1] if decks else 1
            
            for deck_name, games, wins, losses in decks:
                # Deck row container
                row_container = QWidget()
                row_layout = QVBoxLayout(row_container)
                row_layout.setContentsMargins(0, 4, 0, 4)
                row_layout.setSpacing(4)
                
                # Top: Name and stats
                top_row = QHBoxLayout()
                top_row.setSpacing(8)
                
                name_label = QLabel(deck_name[:30])
                name_label.setStyleSheet("color: rgba(255, 255, 255, 0.9); font-size: 11px; font-weight: 500;")
                top_row.addWidget(name_label)
                
                top_row.addStretch()
                
                win_rate = (wins / games * 100) if games > 0 else 0
                
                # Calculate confidence interval (95%)
                if games >= 3:
                    import math
                    p = wins / games
                    z = 1.96  # 95% confidence
                    se = math.sqrt(p * (1 - p) / games)
                    ci_lower = max(0, (p - z * se) * 100)
                    ci_upper = min(100, (p + z * se) * 100)
                    ci_text = f" (CI: {ci_lower:.0f}%-{ci_upper:.0f}%)"
                else:
                    ci_text = " (Low data)"
                
                stats_label = QLabel(f"{games} games • {win_rate:.0f}% WR{ci_text}")
                stats_label.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 10px;")
                top_row.addWidget(stats_label)
                
                row_layout.addLayout(top_row)
                
                # Bottom: Progress bar
                bar_container = QFrame()
                bar_container.setFixedHeight(6)
                bar_container.setStyleSheet("""
                    QFrame {
                        background-color: rgba(255, 255, 255, 0.05);
                        border-radius: 3px;
                    }
                """)
                
                bar_layout = QHBoxLayout(bar_container)
                bar_layout.setContentsMargins(0, 0, 0, 0)
                bar_layout.setSpacing(0)
                
                # Filled portion based on win rate (0-100%)
                fill_percentage = int(win_rate)
                fill_bar = QFrame()
                fill_bar.setFixedHeight(6)
                
                # Color based on win rate
                if win_rate >= 60:
                    gradient_color = "stop:0 #66BB6A, stop:1 #81C784"  # Green
                elif win_rate >= 50:
                    gradient_color = "stop:0 #4A9FD8, stop:1 #6BB6E8"  # Blue
                else:
                    gradient_color = "stop:0 #EF5350, stop:1 #E57373"  # Red
                
                fill_bar.setStyleSheet(f"""
                    QFrame {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            {gradient_color});
                        border-radius: 3px;
                    }}
                """)
                bar_layout.addWidget(fill_bar, fill_percentage)
                bar_layout.addStretch(100 - fill_percentage)
                
                row_layout.addWidget(bar_container)
                
                self.deck_list_layout.addWidget(row_container)
        
        except Exception as e:
            print(f"Error updating deck usage: {e}")
    
    def update_recent_battles(self):
        """Update recent battles with modern styling"""
        try:
            # Clear existing
            while self.battles_list_layout.count():
                child = self.battles_list_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            battles = self.db.get_recent_battles(limit=10)
            
            if not battles:
                no_data = QLabel("No battles yet")
                no_data.setStyleSheet("color: rgba(255, 255, 255, 0.3); font-size: 11px; font-style: italic;")
                self.battles_list_layout.addWidget(no_data)
                return
            
            for battle in battles:
                timestamp, my_deck, opp_deck, result, my_rank, log_file = battle
                
                battle_row = QPushButton()  # Changed to QPushButton for clickability
                battle_row.setFixedHeight(32)
                battle_row.setCursor(Qt.CursorShape.PointingHandCursor)
                battle_row.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255, 255, 255, 0.02);
                        border-radius: 4px;
                        border: none;
                        text-align: left;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 255, 255, 0.06);
                    }
                    QPushButton:pressed {
                        background-color: rgba(255, 255, 255, 0.08);
                    }
                """)
                
                # Connect click event
                if log_file:
                    battle_row.clicked.connect(lambda checked=False, lf=log_file: self.open_log_file(lf))
                    battle_row.setToolTip(f"Click to open log file: {os.path.basename(log_file) if log_file else 'N/A'}")
                
                layout = QHBoxLayout(battle_row)
                layout.setContentsMargins(10, 4, 10, 4)
                layout.setSpacing(10)
                
                # Result indicator
                result_indicator = QFrame()
                result_indicator.setFixedSize(4, 20)
                color = "#66BB6A" if result == "Win" else "#EF5350"
                result_indicator.setStyleSheet(f"""
                    QFrame {{
                        background-color: {color};
                        border-radius: 2px;
                    }}
                """)
                layout.addWidget(result_indicator)
                
                # Decks
                decks_text = f"{my_deck[:18]} vs {opp_deck[:18]}"
                decks_label = QLabel(decks_text)
                decks_label.setStyleSheet("color: rgba(255, 255, 255, 0.8); font-size: 10px;")
                layout.addWidget(decks_label)
                
                layout.addStretch()
                
                # Time
                try:
                    time_obj = datetime.fromisoformat(timestamp)
                    time_str = time_obj.strftime("%m/%d %H:%M")
                except:
                    time_str = "Unknown"
                
                time_label = QLabel(time_str)
                time_label.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 9px;")
                time_label.setFixedWidth(65)
                layout.addWidget(time_label)
                
                self.battles_list_layout.addWidget(battle_row)
        
        except Exception as e:
            print(f"Error updating recent battles: {e}")
    
    def open_log_file(self, log_file_path):
        """Open the battle log file in default text editor"""
        try:
            if not log_file_path:
                print("No log file associated with this battle")
                return
            
            # Check if it's a full path or just a filename
            if not os.path.isabs(log_file_path):
                # Try in Logs directory
                log_file_path = os.path.join(BASE_DIR, "Logs", log_file_path)
            
            if not os.path.exists(log_file_path):
                print(f"Log file not found: {log_file_path}")
                return
            
            # Open with default application
            if sys.platform == 'win32':
                os.startfile(log_file_path)
            elif sys.platform == 'darwin':  # macOS
                import subprocess
                subprocess.run(['open', log_file_path])
            else:  # linux
                import subprocess
                subprocess.run(['xdg-open', log_file_path])
                
            print(f"Opened log file: {log_file_path}")
        except Exception as e:
            print(f"Error opening log file: {e}")
    
    def refresh_battle_management(self):
        """Refresh the battle management list"""
        try:
            # Clear existing
            while self.battle_mgmt_list_layout.count():
                child = self.battle_mgmt_list_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            # Get recent battles with IDs
            import sqlite3
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, my_deck, opponent_deck, result, my_rank, log_file 
                FROM battles 
                ORDER BY timestamp DESC 
                LIMIT 20
            """)
            battles = cursor.fetchall()
            conn.close()
            
            if not battles:
                no_data = QLabel("No battles found")
                no_data.setStyleSheet("color: rgba(255, 255, 255, 0.3); font-size: 11px; font-style: italic; padding: 8px;")
                self.battle_mgmt_list_layout.addWidget(no_data)
                return
            
            for battle in battles:
                battle_id, timestamp, my_deck, opp_deck, result, my_rank, log_file = battle
                
                # Create battle row container
                battle_row = QFrame()
                battle_row.setStyleSheet("""
                    QFrame {
                        background-color: rgba(255, 255, 255, 0.02);
                        border-radius: 4px;
                        border: 1px solid rgba(255, 255, 255, 0.05);
                    }
                    QFrame:hover {
                        background-color: rgba(255, 255, 255, 0.04);
                    }
                """)
                battle_row.setFixedHeight(40)
                
                row_layout = QHBoxLayout(battle_row)
                row_layout.setContentsMargins(8, 4, 8, 4)
                row_layout.setSpacing(8)
                
                # Result indicator
                result_indicator = QFrame()
                result_indicator.setFixedSize(4, 28)
                color = "#66BB6A" if result == "Win" else "#EF5350"
                result_indicator.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
                row_layout.addWidget(result_indicator)
                
                # Battle info
                info_layout = QVBoxLayout()
                info_layout.setSpacing(2)
                
                # Decks line
                decks_text = f"{my_deck[:20]} vs {opp_deck[:20]}"
                decks_label = QLabel(decks_text)
                decks_label.setStyleSheet("color: rgba(255, 255, 255, 0.9); font-size: 10px; font-weight: 500;")
                info_layout.addWidget(decks_label)
                
                # Time and rank line
                try:
                    time_obj = datetime.fromisoformat(timestamp)
                    time_str = time_obj.strftime("%m/%d/%Y %H:%M:%S")
                except:
                    time_str = timestamp
                
                rank_str = f"Rank: {my_rank}" if my_rank else "Rank: N/A"
                meta_text = f"{time_str} • {rank_str}"
                meta_label = QLabel(meta_text)
                meta_label.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 9px;")
                info_layout.addWidget(meta_label)
                
                row_layout.addLayout(info_layout)
                row_layout.addStretch()
                
                # Delete button
                delete_btn = QPushButton("Delete")
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(239, 83, 80, 0.2);
                        color: #EF5350;
                        border: 1px solid rgba(239, 83, 80, 0.3);
                        border-radius: 4px;
                        padding: 4px 12px;
                        font-size: 10px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background-color: rgba(239, 83, 80, 0.3);
                        border: 1px solid rgba(239, 83, 80, 0.5);
                    }
                    QPushButton:pressed {
                        background-color: rgba(239, 83, 80, 0.4);
                    }
                """)
                delete_btn.setFixedSize(60, 28)
                delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                delete_btn.clicked.connect(lambda checked=False, bid=battle_id: self.delete_battle(bid))
                row_layout.addWidget(delete_btn)
                
                self.battle_mgmt_list_layout.addWidget(battle_row)
            
            # Add stretch at the end
            self.battle_mgmt_list_layout.addStretch()
            
            print(f"Loaded {len(battles)} battles for management")
            
        except Exception as e:
            print(f"Error refreshing battle management: {e}")
            import traceback
            traceback.print_exc()
    
    def delete_battle(self, battle_id):
        """Delete a battle from the database"""
        try:
            # Confirm deletion
            reply = QMessageBox.question(
                self, 
                'Confirm Delete',
                f'Are you sure you want to delete battle #{battle_id}?\n\nThis will also update your session stats.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                return
            
            import sqlite3
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            # Get battle info before deleting (for session stats update)
            cursor.execute("SELECT timestamp, result FROM battles WHERE id = ?", (battle_id,))
            battle_data = cursor.fetchone()
            
            if not battle_data:
                print(f"Battle {battle_id} not found")
                conn.close()
                return
            
            timestamp, result = battle_data
            
            # Delete the battle
            cursor.execute("DELETE FROM battles WHERE id = ?", (battle_id,))
            conn.commit()
            
            # Update session stats
            try:
                battle_date = datetime.fromisoformat(timestamp).date()
                cursor.execute("SELECT wins, losses FROM session_stats WHERE date = ?", (battle_date,))
                stats = cursor.fetchone()
                
                if stats:
                    wins, losses = stats
                    if result.upper() == "WIN":
                        wins = max(0, wins - 1)
                    else:
                        losses = max(0, losses - 1)
                    
                    cursor.execute("""
                        UPDATE session_stats 
                        SET wins = ?, losses = ? 
                        WHERE date = ?
                    """, (wins, losses, battle_date))
                    conn.commit()
                    print(f"✓ Session stats updated for {battle_date}: {wins}-{losses}")
            except Exception as stats_error:
                print(f"Warning: Could not update session stats: {stats_error}")
            
            conn.close()
            
            print(f"✓ Deleted battle #{battle_id}")
            
            # Refresh the list and main stats
            self.refresh_battle_management()
            self.load_stats()
            
        except Exception as e:
            print(f"Error deleting battle: {e}")
            import traceback
            traceback.print_exc()
    
    def apply_modern_style(self):
        """Apply modern glass-morphism styling"""
        self.setStyleSheet("""
            /* Main glass container */
            QFrame#glassContainer {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(15, 15, 15, 0.85),
                    stop:1 rgba(10, 10, 10, 0.88));
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
            
            /* Title bar */
            QFrame#titleBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(25, 25, 25, 0.5),
                    stop:1 rgba(15, 15, 15, 0.3));
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            
            QLabel#titleText {
                color: rgba(255, 255, 255, 0.95);
                font-family: 'Segoe UI', 'San Francisco', Arial;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 2px;
            }
            
            /* Buttons */
            QPushButton#minBtn, QPushButton#closeBtn {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.7);
                font-size: 18px;
                font-weight: 300;
            }
            
            QPushButton#minBtn:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.9);
            }
            
            QPushButton#closeBtn:hover {
                background-color: rgba(239, 83, 80, 0.3);
                border-color: rgba(239, 83, 80, 0.5);
                color: #EF5350;
            }
            
            /* Scroll area */
            QScrollArea#scrollArea {
                background-color: transparent;
                border: none;
            }
            
            QWidget#contentWidget {
                background-color: transparent;
            }
            
            /* Scrollbar */
            QScrollBar:vertical {
                background-color: transparent;
                width: 8px;
                margin: 0px;
            }
            
            QScrollBar::handle:vertical {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                min-height: 20px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: rgba(255, 255, 255, 0.15);
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            
            /* Section cards */
            QFrame#graphCard, QFrame#deckCard, QFrame#battlesCard, QFrame#limitlessCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 0.03),
                    stop:1 rgba(255, 255, 255, 0.01));
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 10px;
            }
            
            QLabel#graphTitle, QLabel#sectionHeader {
                color: rgba(255, 255, 255, 0.7);
                font-family: 'Segoe UI', 'San Francisco', Arial;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.5px;
            }
            
            /* Limitless button */
            QPushButton#limitlessBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(74, 159, 216, 0.3),
                    stop:1 rgba(107, 182, 232, 0.3));
                border: 1px solid rgba(74, 159, 216, 0.4);
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.95);
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
                font-weight: 600;
                padding: 8px 16px;
            }
            
            QPushButton#limitlessBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(74, 159, 216, 0.5),
                    stop:1 rgba(107, 182, 232, 0.5));
                border-color: rgba(74, 159, 216, 0.6);
            }
            
            QLabel#placeholder {
                color: rgba(255, 255, 255, 0.3);
                font-size: 10px;
                font-style: italic;
            }
            
            /* Tab Widget */
            QTabWidget#mainTabs {
                background-color: transparent;
                border: none;
            }
            
            QTabWidget::pane {
                background: transparent;
                border: none;
                border-top: 1px solid rgba(255, 255, 255, 0.05);
            }
            
            QTabBar::tab {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                color: rgba(255, 255, 255, 0.5);
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
                font-weight: 600;
                padding: 8px 20px;
                margin-right: 4px;
            }
            
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(74, 159, 216, 0.15),
                    stop:1 rgba(74, 159, 216, 0.05));
                border-color: rgba(74, 159, 216, 0.3);
                color: rgba(255, 255, 255, 0.95);
            }
            
            QTabBar::tab:hover:!selected {
                background: rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.7);
            }
            
            /* Settings cards and buttons */
            QFrame#settingsCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 0.03),
                    stop:1 rgba(255, 255, 255, 0.01));
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 10px;
            }
            
            QPushButton#settingsBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 0.06),
                    stop:1 rgba(255, 255, 255, 0.02));
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.9);
                font-family: 'Segoe UI', Arial;
                font-size: 12px;
                font-weight: 500;
                padding: 8px 16px;
            }
            
            QPushButton#settingsBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(74, 159, 216, 0.3),
                    stop:1 rgba(74, 159, 216, 0.1));
                border-color: rgba(74, 159, 216, 0.4);
            }
            
            QLabel#settingsDesc {
                color: rgba(255, 255, 255, 0.5);
                font-size: 11px;
                font-style: italic;
            }
            
            /* Buy Me a Coffee button */
            QPushButton#coffeeBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(255, 221, 87, 0.4),
                    stop:1 rgba(255, 193, 7, 0.4));
                border: 2px solid rgba(255, 221, 87, 0.6);
                border-radius: 25px;
                color: rgba(255, 255, 255, 0.95);
                font-family: 'Segoe UI', Arial;
                font-size: 14px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            
            QPushButton#coffeeBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(255, 221, 87, 0.6),
                    stop:1 rgba(255, 193, 7, 0.6));
                border-color: rgba(255, 221, 87, 0.8);
            }
        """)


def main():
    """Run the stats window standalone"""
    app = QApplication(sys.argv)
    
    window = StatsWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
