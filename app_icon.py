"""The app's own taskbar identity and icon.

The HUD and the dashboard run under pythonw.exe, so Windows grouped their
windows (the opponent decklist window among them) under Python and showed
Python's icon on the taskbar. An explicit AppUserModelID gives the process a
taskbar button of its own, which then takes icon.ico from the window.
Call install(app) right after creating the QApplication, before any window.
"""
import os
import sys

APP_ID = "PokemonTCGLiveMonitor.App"
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")


def install(app):
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
    if os.path.exists(ICON):
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(ICON))
