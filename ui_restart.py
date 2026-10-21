"""
Restart the UI in place (Advanced -> Restart app, or after a theme change).

The dashboard usually lives inside the overlay process. A restart leaves a
note (.ui_restart.json) and quits; the monitor sees the note and relaunches
the overlay at once (not counted as a crash), and the new overlay reads the
note: no launch prompts again, and the dashboard reopens on the same tab.
A standalone dashboard relaunches itself.
"""

import json
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARKER = os.path.join(BASE_DIR, ".ui_restart.json")
MAX_AGE_S = 60.0


def request(tab=None):
    """Write the note for the next UI process."""
    try:
        with open(MARKER, "w", encoding="utf-8") as handle:
            json.dump({"time": time.time(), "tab": tab}, handle)
    except OSError:
        pass


def pending():
    """True while a fresh note waits (the monitor's fast path)."""
    try:
        return time.time() - os.path.getmtime(MARKER) < MAX_AGE_S
    except OSError:
        return False


def take():
    """The note, once (deleted on read); None when there is none or it's stale."""
    try:
        with open(MARKER, "r", encoding="utf-8") as handle:
            note = json.load(handle)
    except (OSError, ValueError):
        return None
    finally:
        try:
            os.remove(MARKER)
        except OSError:
            pass
    if not isinstance(note, dict) or time.time() - float(note.get("time") or 0) > MAX_AGE_S:
        return None
    return note


def gui_python():
    """pythonw next to the running interpreter (no console window)."""
    exe = sys.executable
    candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return candidate if os.path.exists(candidate) else exe


def relaunch_dashboard(tab=None):
    """Standalone dashboard: start a fresh one (it reads the note), then the
    caller quits."""
    request(tab)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([gui_python(), os.path.join(BASE_DIR, "StatsUI.py")], cwd=BASE_DIR, creationflags=flags,
                     close_fds=True)
