"""
Launch TCG Live Monitor in Headless Mode
No console window - only overlay and stats UI visible
"""

import os
import sys
import tkinter as tk
from tkinter import messagebox

from startup_utils import launch_monitor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    result = launch_monitor(BASE_DIR, headless=True)
    if not result["ok"]:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Headless Launch Failed", result["error"])
        root.destroy()
        sys.exit(1)
