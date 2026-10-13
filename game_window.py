"""
Lightweight helpers for locating the Pokemon TCG Live window.

Shared by the monitor, the battle-end automation, the Continue blocker and
RankDetector so every component agrees on what "the game window" is.

Design notes
------------
* Matching is on the EXACT window title ("Pokémon TCG Live" / "Pokemon TCG
  Live"), never a substring. Substring matching used to pick up our own
  "Pokemon TCG Live Monitor - Startup Manager" window and browser tabs.
* The process is made per-monitor DPI aware once, so GetWindowRect, mss
  screen captures and SetCursorPos all speak physical pixels.
* No mss/GDI objects are created here (see BUG-010 in the dev vault).
"""

import os
import time

try:
    import win32gui
    import win32process
    WIN32_AVAILABLE = True
except Exception:  # non-Windows / tests
    win32gui = None
    win32process = None
    WIN32_AVAILABLE = False

GAME_TITLES = {"pokemon tcg live", "pokémon tcg live"}
GAME_PROCESS_NAMES = {"pokemon tcg live.exe", "pokémon tcg live.exe"}

_dpi_done = False


def ensure_dpi_aware():
    """Make this process per-monitor DPI aware (idempotent, Windows only)."""
    global _dpi_done
    if _dpi_done or os.name != "nt":
        return
    _dpi_done = True
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def is_game_title(title):
    return (title or "").strip().casefold() in GAME_TITLES


def _process_names_toolhelp():
    """Executable names of every process via CreateToolhelp32Snapshot - one
    kernel snapshot, a few milliseconds. (psutil's per-process name lookup
    cost ~3 s of CPU for ~600 processes, every 5 s while idle.)"""
    return [name for _pid, name in process_list()]


def process_list():
    """[(pid, executable name)] of every process, from one Toolhelp snapshot
    (Windows only; raises elsewhere)."""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == wintypes.HANDLE(-1).value:
        raise OSError("snapshot failed")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        procs = []
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            procs.append((entry.th32ProcessID, entry.szExeFile))
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
        return procs
    finally:
        kernel32.CloseHandle(snap)


def _is_game_name(name):
    name = (name or "").casefold()
    return name in GAME_PROCESS_NAMES or "pokemon tcg live" in name or "pokémon tcg live" in name


def is_game_process_running():
    """Is the game running? Fast Windows snapshot; psutil as a fallback."""
    if os.name == "nt":
        try:
            return any(_is_game_name(n) for n in _process_names_toolhelp())
        except Exception:
            pass
    try:
        import psutil
    except Exception:
        return False
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info.get("name") or "").casefold()
        except Exception:
            continue
        if name in GAME_PROCESS_NAMES or "pokemon tcg live" in name or "pokémon tcg live" in name:
            return True
    return False


def _window_rect(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return {
        "hwnd": hwnd,
        "title": win32gui.GetWindowText(hwnd),
        "left": left,
        "top": top,
        "width": right - left,
        "height": bottom - top,
    }


def find_game_hwnd():
    """Return the hwnd of the visible game window, or None."""
    if not WIN32_AVAILABLE:
        return None
    ensure_dpi_aware()
    found = []

    def _cb(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd) and is_game_title(win32gui.GetWindowText(hwnd)):
                if win32gui.GetClassName(hwnd) != "ConsoleWindowClass":
                    found.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        return None
    return found[0] if found else None


def game_rect(hwnd=None):
    """Return the window rect dict for hwnd (or the found game window)."""
    if not WIN32_AVAILABLE:
        return None
    hwnd = hwnd or find_game_hwnd()
    if not hwnd:
        return None
    try:
        if not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
            return None
        rect = _window_rect(hwnd)
    except Exception:
        return None
    if rect["width"] <= 0 or rect["height"] <= 0:
        return None
    return rect


def is_foreground(hwnd):
    """True if hwnd (or a window it owns) is the foreground window."""
    if not WIN32_AVAILABLE or not hwnd:
        return False
    try:
        fg = win32gui.GetForegroundWindow()
        if fg == hwnd:
            return True
        # Treat the game's own child/owned windows as foreground too.
        _, fg_pid = win32process.GetWindowThreadProcessId(fg)
        _, game_pid = win32process.GetWindowThreadProcessId(hwnd)
        return bool(fg_pid) and fg_pid == game_pid
    except Exception:
        return False


class GameWindowCache:
    """Caches the game hwnd and re-validates it cheaply.

    EnumWindows only runs when the cached handle is gone or every
    `refresh_s` seconds, so callers can poll rect() at high frequency.
    """

    def __init__(self, refresh_s=5.0):
        self.refresh_s = refresh_s
        self._hwnd = None
        self._checked = 0.0

    def hwnd(self):
        now = time.time()
        valid = False
        if self._hwnd and WIN32_AVAILABLE:
            try:
                valid = win32gui.IsWindow(self._hwnd) and is_game_title(win32gui.GetWindowText(self._hwnd))
            except Exception:
                valid = False
        if not valid or now - self._checked > self.refresh_s:
            self._hwnd = find_game_hwnd()
            self._checked = now
        return self._hwnd

    def rect(self):
        h = self.hwnd()
        return game_rect(h) if h else None
