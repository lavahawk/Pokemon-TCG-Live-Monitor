"""
Launch TCG Live Monitor in Headless Mode
No console window - only overlay and stats UI visible
"""

import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MONITOR_SCRIPT = os.path.join(BASE_DIR, "TCGLiveMonitor.py")

if __name__ == "__main__":
    print("Starting TCG Live Monitor in headless mode...")
    print("No console will be shown - only overlay and stats UI")
    print("Use the 'Close Application' button in Advanced tab to exit")
    
    # Launch without console window
    if os.name == 'nt':  # Windows
        subprocess.Popen(
            [sys.executable, MONITOR_SCRIPT, "--headless"],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    else:  # Linux/Mac
        subprocess.Popen(
            [sys.executable, MONITOR_SCRIPT, "--headless"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    
    print("✓ Headless monitor started!")
    print("✓ Check your system tray or use the overlay UI")
