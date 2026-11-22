"""
Adds the current Limitless tournament opponent as a friend in Pokemon TCG
Live, like a person would: copy their name, then Profile -> Friends ->
Add friend -> paste -> send.

Built on ptcgl_import's OCR clicking (targets are found by reading the
screen, never at fixed pixels; Esc stops it; clicks only go to the game while
it is in front). It never interrupts a battle: it waits, without touching the
game, until the main menu's PROFILE tab is on screen.

    handle_new_opponent("Bob", "https://play.limitlesstcg.com/.../match/...")
"""

import json
import os
import re
import threading
import time

import game_window
from ptcgl_import import NAV, STEP_S, ImportStopped, PTCGLImporter, Screen, user32

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DONE_FILE = os.path.join(BASE_DIR, ".friend_requests.json")  # shared by every process
# Where FRIENDS / ADD FRIEND were last found (fractions of the client size),
# so the next run clicks straight there instead of reading the whole screen.
UI_CACHE_FILE = os.path.join(BASE_DIR, ".friend_ui.json")
WAIT_MENU_S = 15 * 60   # a game of the match may still be running
WHOLE = (0.0, 0.0, 1.0, 1.0)
# The friends list / add-friend panel slides in from the left edge, below the
# nav bar ("ENTER SCREEN NAME" box on top, SEND under it).
FRIEND_PANEL = ("L", 0.65, 0.08, 0.5)
# Where the name box's placeholder and the SEND button sit, in window heights
# from the client's top-left (x0, y0, x1, y1). Busy friend cards behind them
# defeat a whole-panel OCR read, so these small bands are read one line at a
# time. Measured at 1920x1080 (the panel scales with the window height).
NAME_BOX_H = (0.175, 0.085, 0.45, 0.138)
SEND_BOX_H = (0.205, 0.26, 0.415, 0.315)

BLOCK_MAX_S = 25        # the input lock always lets go after this long
ASK_TIMEOUT_S = 60      # no answer to the popup = "Not now"

_lock = threading.Lock()
_running = set()


_CURSOR_IDS = (32512, 32513, 32514, 32515, 32516, 32642, 32643, 32644, 32645, 32646, 32648, 32649, 32650)


def hide_cursor():
    """Swap every system cursor for a blank one: the clicks still go
    through the real cursor (the game ignores posted clicks), but nothing
    visibly jumps. restore_cursor() puts the user's cursor scheme back."""
    import ctypes
    user32_ = ctypes.windll.user32
    and_mask = (ctypes.c_ubyte * 128)(*([0xFF] * 128))
    xor_mask = (ctypes.c_ubyte * 128)(*([0x00] * 128))
    user32_.CreateCursor.restype = ctypes.c_void_p
    user32_.SetSystemCursor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    for cid in _CURSOR_IDS:
        blank = user32_.CreateCursor(None, 0, 0, 32, 32, and_mask, xor_mask)
        if blank:
            user32_.SetSystemCursor(blank, cid)  # takes ownership


def restore_cursor():
    import ctypes
    ctypes.windll.user32.SystemParametersInfoW(0x0057, 0, None, 0)  # SPI_SETCURSORS


class InputBlocker:
    """Holds the player's own mouse and keyboard while the add-friend clicks
    run, so a stray click can't land mid-way. Low-level hooks drop physical
    input and let the automation's injected clicks and keys through. Esc
    (physical) cancels and lets go; it always lets go after BLOCK_MAX_S.
    No admin rights needed (unlike BlockInput)."""

    def __init__(self, on_escape=None, max_s=BLOCK_MAX_S):
        self.on_escape = on_escape or (lambda: None)
        self.max_s = max_s
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, name="friend-input-lock", daemon=True)
        self._thread.start()
        self._ready.wait(2)
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    def release(self):
        import ctypes
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        if self._thread:
            self._thread.join(2)

    def _run(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]

        class KBD(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        class MOUSE(ctypes.Structure):
            _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        def on_key(code, wparam, lparam):
            if code == 0:
                info = ctypes.cast(lparam, ctypes.POINTER(KBD)).contents
                if not info.flags & 0x10:          # LLKHF_INJECTED: ours pass
                    if info.vkCode == 0x1B and wparam in (0x100, 0x104):  # Esc down
                        self.on_escape()
                    return 1
            return user32.CallNextHookEx(None, code, wparam, lparam)

        def on_mouse(code, wparam, lparam):
            if code == 0:
                info = ctypes.cast(lparam, ctypes.POINTER(MOUSE)).contents
                if not info.flags & 0x01:          # LLMHF_INJECTED: ours pass
                    return 1
            return user32.CallNextHookEx(None, code, wparam, lparam)

        key_proc, mouse_proc = HOOKPROC(on_key), HOOKPROC(on_mouse)  # keep alive
        self._thread_id = kernel32.GetCurrentThreadId()
        hooks = [user32.SetWindowsHookExW(13, key_proc, None, 0),     # WH_KEYBOARD_LL
                 user32.SetWindowsHookExW(14, mouse_proc, None, 0)]   # WH_MOUSE_LL
        timer = user32.SetTimer(None, 0, int(self.max_s * 1000), None)
        msg = wintypes.MSG()
        try:
            try:
                hide_cursor()
            except Exception:
                pass
            self._ready.set()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0113:   # WM_TIMER: safety release
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            try:
                restore_cursor()
            except Exception:
                pass
            if timer:
                user32.KillTimer(None, timer)
            for hook in hooks:
                if hook:
                    user32.UnhookWindowsHookEx(hook)
            self._thread_id = None


def F_norm(text):
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def opponent_from_match_link(text):
    """Opponent's name from a Limitless dashboard match link ("R1 vs Name",
    the name maybe on its own line, maybe followed by more lines), or ""."""
    match = re.search(r"\bvs\.?[ \t]*(?:\r?\n[ \t]*)?([^\r\n]{1,40})", text or "", flags=re.IGNORECASE)
    if not match:
        return ""
    name = re.sub(r"\s+", " ", match.group(1)).strip()
    # Drop trailing status words some links carry ("Active Match", a record).
    name = re.sub(r"\s+(?:active match|\(?\d+-\d+(?:-\d+)?\)?)$", "", name, flags=re.IGNORECASE).strip()
    return name


def auto_add_enabled():
    try:
        from app_settings import load_app_settings
        return bool(load_app_settings().get("limitless_auto_add_friend", True))
    except Exception:
        return True


def copy_to_clipboard(text):
    import win32clipboard
    for _attempt in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception:
            time.sleep(0.2)
    return False


def _claim(key):
    """True once per match across processes (overlay + a standalone dashboard)."""
    with _lock:
        try:
            with open(DONE_FILE, "r", encoding="utf-8") as handle:
                done = json.load(handle)
        except Exception:
            done = {}
        if key in done:
            return False
        cutoff = time.time() - 7 * 86400
        done = {k: v for k, v in done.items() if isinstance(v, (int, float)) and v > cutoff}
        done[key] = time.time()
        try:
            with open(DONE_FILE, "w", encoding="utf-8") as handle:
                json.dump(done, handle)
        except OSError:
            pass
        return True


def handle_new_opponent(opponent, match_url="", status=None, ask=None, shade=None):
    """Copy the name now; add the friend in the background (once per match).
    ask(name) -> bool is asked (a popup) once the main menu is up; None = yes."""
    opponent = (opponent or "").strip()
    status = status or (lambda message: None)
    if not opponent:
        return
    if copy_to_clipboard(opponent):
        status(f"Copied opponent name: {opponent}")
    if not auto_add_enabled():
        return
    key = f"{match_url}|{opponent}".lower()
    if key in _running or not _claim(key):
        return
    _running.add(key)

    def work():
        try:
            ok, message = FriendAdder(opponent, status=status, ask=ask, shade=shade).run()
            status(message)
            print(f"[Limitless] {message}")
        finally:
            _running.discard(key)

    threading.Thread(target=work, name="ptcgl-add-friend", daemon=True).start()


class FriendAdder(PTCGLImporter):
    def __init__(self, name, status=None, cancel=None, ask=None, shade=None):
        super().__init__(name, name=None, status=status, cancel=cancel)
        self.friend = name
        self.ask = ask
        # shade(op, *args) dims the game like the deck import: ("show", hwnd,
        # name), ("say", message, progress), ("finish", ok, message).
        self.shade = shade or (lambda *args: None)

    def _wait_for_menu(self, deadline):
        """Wait (no clicks, no focus change) until YOU have the game in front,
        settled for a couple of seconds, on the main menu. Taking the focus
        ourselves lost it again at once to the dashboard or another window."""
        told = False
        front_since = None
        while time.time() < deadline:
            self._check()
            if game_window.is_foreground(self.hwnd) and not user32.IsIconic(self.hwnd):
                front_since = front_since or time.time()
                if time.time() - front_since >= 1.5:
                    try:
                        screen = Screen(self.hwnd)
                        point = screen.find("PROFILE", NAV, deep=False)
                        if point:
                            self._menu = (screen, point)
                            return
                    except Exception:
                        pass
            else:
                front_since = None
            if not told:
                self._say(f"Will add {self.friend} as a friend once you're on the main menu.")
                told = True
            time.sleep(1)
        raise ImportStopped("Gave up adding the friend: the main menu never showed up.")

    @staticmethod
    def _band_text(screen, band_h):
        """(text, centre) of the single text line inside band_h (see NAME_BOX_H)."""
        import cv2
        h = screen.size[1]
        x0, y0, x1, y1 = (int(v * h) for v in band_h)
        x1 = min(x1, screen.size[0])
        gray = cv2.cvtColor(screen.image[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        f = 2.0 * max(1.0, 1080.0 / h)
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        tess = screen._tesseract()
        otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        text = ""
        # as is, inverted, then hard black/white (light label on a grey button)
        for img in (gray, 255 - gray, otsu, 255 - otsu):
            text = tess.image_to_string(img, config="--psm 7").strip()
            if len(re.sub(r"[^A-Za-z]", "", text)) >= 3:
                break
        return text, ((x0 + x1) / 2, (y0 + y1) / 2)

    def _band_has(self, band_h, words, timeout):
        deadline = time.time() + timeout
        while True:
            screen = self._screen()
            text, centre = self._band_text(screen, band_h)
            norm = re.sub(r"[^A-Z]", "", text.upper())
            if any(w in norm for w in words):
                return screen, centre
            if time.time() > deadline:
                return screen, None
            time.sleep(0.25)

    def _wait_send_enabled(self, timeout):
        deadline = time.time() + timeout
        while True:
            screen = self._screen()
            h = screen.size[1]
            x0, y0, x1, y1 = (int(v * h) for v in SEND_BOX_H)
            b, g, r = screen.image[y0:y1, x0:x1].reshape(-1, 3).mean(0)
            if r > 150 and g < 90 and b < 90:
                return screen, ((x0 + x1) / 2, (y0 + y1) / 2)
            if time.time() > deadline:
                return screen, None
            time.sleep(0.1)

    def _find_any(self, labels, region, timeout):
        deadline = time.time() + timeout
        while True:
            screen = self._screen()
            for label in labels:
                point = screen.find(label, region)
                if point:
                    return screen, point
            if time.time() > deadline:
                return screen, None
            time.sleep(0.25)

    def run(self):
        """(ok, message). Never raises."""
        try:
            self.hwnd = game_window.find_game_hwnd()
            if not self.hwnd:
                return False, "Pokémon TCG Live isn't running."
            deadline = time.time() + WAIT_MENU_S
            asked = False
            for attempt in range(3):
                try:
                    self._wait_for_menu(deadline)
                    if self.ask and not asked:
                        asked = True
                        if not self.ask(self.friend):
                            return False, f"Didn't add {self.friend} (their name is on your clipboard)."
                        # The popup had the focus: hand it back to the game.
                        if not self._focus():
                            raise ImportStopped("Stopped: Pokémon TCG Live is no longer in front.")
                        time.sleep(0.1)
                    self.shade("show", self.hwnd, self.friend)
                    time.sleep(0.05)
                    if not game_window.is_foreground(self.hwnd):
                        self._focus()  # the shade must never keep the focus
                    try:
                        with InputBlocker(on_escape=self.cancel.set):
                            result = self._add()
                    except Exception as exc:
                        self._save_failure_shot()
                        self.shade("finish", False, str(exc) or "Stopped")
                        raise
                    self.shade("finish", True, result[1])
                    return result
                except ImportStopped as exc:
                    # Switched away mid-way: wait for the menu again. Esc or
                    # the game closing ends it.
                    if "no longer in front" not in str(exc) or attempt == 2:
                        raise
                    self._say(f"Paused adding {self.friend}; will retry on the main menu.")
            raise ImportStopped("Gave up after 3 tries")
        except ImportStopped as exc:
            return False, f"Add friend: {exc} (their name is on your clipboard)."
        except Exception as exc:
            return False, f"Add friend failed: {exc} (their name is on your clipboard)."

    def _save_failure_shot(self):
        """What the game showed when a step failed: Logs/friend_add_failed.png."""
        try:
            from PIL import Image
            arr = Screen(self.hwnd).image
            img = Image.fromarray(arr[:, :, [2, 1, 0]] if arr.shape[2] >= 3 else arr)
            os.makedirs("Logs", exist_ok=True)
            img.save(os.path.join("Logs", "friend_add_failed.png"))
        except Exception:
            pass

    def _focus(self):
        """Game to the front; returns as soon as it is (not a fixed 0.5 s)."""
        if game_window.is_foreground(self.hwnd):
            return True
        if user32.IsIconic(self.hwnd):
            user32.ShowWindow(self.hwnd, 9)  # SW_RESTORE
        user32.keybd_event(0x12, 0, 0, 0)  # Alt lets SetForegroundWindow work
        user32.SetForegroundWindow(self.hwnd)
        user32.keybd_event(0x12, 0, 2, 0)
        deadline = time.time() + 0.6
        while time.time() < deadline:
            if game_window.is_foreground(self.hwnd):
                return True
            time.sleep(0.03)
        return game_window.is_foreground(self.hwnd)

    # ── remembered spots ────────────────────────────────────────────────
    def _load_cache(self):
        try:
            with open(UI_CACHE_FILE, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def _cached(self, screen, label, any_shape=False):
        """Last known spot of `label` for this window shape, or None
        (any_shape: also one remembered for another window shape)."""
        w, h = screen.size
        spot = self._load_cache().get(label)
        if not spot or (abs(spot[2] - w / h) > 0.01 and not any_shape):
            return None
        return (spot[0] * w, spot[1] * h)

    def _remember(self, screen, label, point):
        w, h = screen.size
        cache = self._load_cache()
        cache[label] = [point[0] / w, point[1] / h, w / h]
        try:
            with open(UI_CACHE_FILE, "w", encoding="utf-8") as handle:
                json.dump(cache, handle)
        except OSError:
            pass

    def _name_box(self, timeout):
        return self._band_has(NAME_BOX_H, ("SCREENNAME", "ENTERSCREEN"), timeout)

    def _open_add_friend(self):
        """From the main menu to the Enter Screen Name box: (screen, centre).
        Fast path clicks the remembered spots and checks the box appeared;
        anything unexpected falls back to reading the screen."""
        screen, profile = getattr(self, "_menu", (None, None))
        if profile is None:
            screen, profile = self._wait_for("PROFILE", NAV)
        self._click(screen, profile)
        self._progress("Opening Friends", 0.3)
        friends = self._cached(screen, "FRIENDS")
        if friends:
            for _try in range(3):
                time.sleep(0.3)
                self._click(self._screen(), friends)
                screen, field = self._name_box(0.7)
                if field:
                    return screen, field
                add = self._cached(screen, "ADD FRIEND")
                if add:
                    self._click(screen, add)
                    screen, field = self._name_box(1.2)
                    if field:
                        return screen, field
        # Slow path: read the screen for each step (and remember the spots).
        screen, field = self._name_box(0.3)
        if field:
            return screen, field
        screen, point = self._find_any(["ADD FRIEND"], WHOLE, 0.5)
        if not point:
            try:
                screen, point = self._wait_for("FRIENDS", WHOLE)
            except ImportStopped:
                # Unreadable (another window shape, say): try where it was
                # last time before giving up.
                screen = self._screen()
                guess = self._cached(screen, "FRIENDS", any_shape=True)
                if not guess:
                    raise
                self._click(screen, guess)
                screen, field = self._name_box(1.5)
                if field:
                    return screen, field
                raise
            self._remember(screen, "FRIENDS", point)
            self._click(screen, point)
            screen, field = self._name_box(1.5)
            if field:
                return screen, field
            screen, point = self._wait_for("ADD FRIEND", WHOLE)
        self._remember(screen, "ADD FRIEND", point)
        self._click(screen, point)
        screen, field = self._name_box(STEP_S)
        if not field:
            raise ImportStopped("Couldn't find the Enter Screen Name box")
        return screen, field

    def _progress(self, message, value):
        self._say(message)
        try:
            self.shade("say", message, value)
        except Exception:
            pass

    def _add(self):
        """Profile -> Friends -> Add friend -> type -> Send. Game in front."""
        self._progress("Opening Profile", 0.12)
        screen, field = self._open_add_friend()
        self._progress(f"Typing {self.friend}", 0.65)
        self._click(screen, field)
        time.sleep(0.15)
        copy_to_clipboard(self.friend)  # still there to paste by hand
        # Typed key by key (Unity text boxes ignore a synthetic Ctrl+V).
        self._type(self.friend)
        # SEND (under the box) turns red once a name is typed; its label
        # reads poorly through OCR, so the colour decides.
        screen, send = self._wait_send_enabled(3)
        if not send:
            raise ImportStopped(f"Typed {self.friend} but the SEND button never lit up")
        self._progress("Sending the request", 0.9)
        self._click(screen, send)
        return True, f"Sent a friend request to {self.friend} in Pokémon TCG Live."
