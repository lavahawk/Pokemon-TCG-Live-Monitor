"""
Launch TCG Live Monitor in Headless Mode
No console window - only overlay and stats UI visible
"""

import os
import sys

from startup_utils import launch_monitor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    result = launch_monitor(BASE_DIR, headless=True)
    if not result["ok"]:
        from qt_dialogs import show_message
        show_message("Headless Launch Failed", result["error"], error=True)
        sys.exit(1)
