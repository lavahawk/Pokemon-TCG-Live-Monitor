"""
Imports a decklist into Pokemon TCG Live by driving its menus, like a person:
Decks -> Create a deck -> Import settings "Rarest owned" -> Import (from the
clipboard) -> rename the new deck (optional).

Every target is found by reading the screen (Tesseract OCR) inside a region
given as fractions of the game's client area, then clicked where its text
was found - never at fixed pixels. PTCGL pins its menus to the window edges,
so proportions alone break on other aspect ratios (a 32:9 fullscreen and a
16:9 window put "DECKS" in different places); reading the text works on
both. Each step waits for the screen it expects and gives up with a clear
reason instead of clicking blind.

Clicks go only to the game while it's in the foreground (AutoClicker's
Unity-safe click); if the user switches away the import stops.

    importer = PTCGLImporter(text, name, status=print)
    ok, message = importer.run()
"""

import ctypes
import difflib
import os
import re
import threading
import time

import numpy as np

import game_window

# Regions (x0, y0, x1, y1) as fractions of the client area.
NAV = (0.0, 0.0, 0.62, 0.11)          # HOME DECKS PROFILE ... (top-left)
DECK_GRID = (0.0, 0.08, 0.68, 0.75)   # deck tiles incl. "Create a deck"
DIALOG = (0.2, 0.15, 0.8, 0.9)        # centred dialogs
RIGHT_PANEL = (0.55, 0.0, 1.0, 0.45)  # deck editor header / rename panel
EDITOR = (0.0, 0.0, 0.7, 0.2)         # "CARD LIBRARY"

WAIT_MENU_S = 120     # how long to wait for the main menu (e.g. a match is on)
STEP_S = 12           # how long each screen may take to appear
OCR_HEIGHT = 2160     # OCR runs on crops scaled as if the window were this tall

user32 = ctypes.windll.user32

MINIMIZE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".minimize_dashboard")


def request_minimize_dashboard():
    """Ask the overlay (it polls every second) to hide the dashboard, which
    stays on top of the game."""
    try:
        with open(MINIMIZE_FILE, "w", encoding="utf-8") as handle:
            handle.write(str(time.time()))
    except OSError:
        pass


def take_minimize_request(max_age=15.0):
    """True once for a fresh request (the overlay's side)."""
    try:
        fresh = time.time() - os.path.getmtime(MINIMIZE_FILE) < max_age
        os.remove(MINIMIZE_FILE)
        return fresh
    except OSError:
        return False


class ImportStopped(Exception):
    pass


def _norm(text):
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _similar(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    return 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()


class Screen:
    """One capture of the game's client area plus OCR on parts of it."""

    def __init__(self, hwnd):
        import win32gui
        import mss
        game_window.ensure_dpi_aware()
        _l, _t, w, h = win32gui.GetClientRect(hwnd)
        x, y = win32gui.ClientToScreen(hwnd, (0, 0))
        self.origin = (x, y)
        self.size = (w, h)
        with mss.mss() as grabber:
            shot = grabber.grab({"left": x, "top": y, "width": w, "height": h})
        self.image = np.asarray(shot)[:, :, :3]  # BGR
        self._words = {}

    @classmethod
    def from_image(cls, image):
        """For tests: a saved screenshot (BGR array) as if it were the game."""
        screen = cls.__new__(cls)
        screen.origin = (0, 0)
        screen.size = (image.shape[1], image.shape[0])
        screen.image = image
        screen._words = {}
        return screen

    def _prepared(self, region):
        """(gray crop upscaled to ~2160p text size, scale, x0, y0) of `region`."""
        import cv2
        w, h = self.size
        x0, y0, x1, y1 = int(region[0] * w), int(region[1] * h), int(region[2] * w), int(region[3] * h)
        gray = cv2.cvtColor(self.image[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        scale = min(3.0, max(1.0, OCR_HEIGHT / float(max(1, h))))
        return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC), scale, x0, y0

    @staticmethod
    def _tesseract():
        import pytesseract
        from RankDetector import _find_tesseract
        pytesseract.pytesseract.tesseract_cmd = _find_tesseract()
        return pytesseract

    def words(self, region):
        """[(text, conf, (x, y, w, h) in client px)] read inside `region`
        (whole-region pass: fast, finds most labels)."""
        if region in self._words:
            return self._words[region]
        tess = self._tesseract()
        gray, scale, x0, y0 = self._prepared(region)
        found = []
        for img in (gray, 255 - gray):  # light-on-dark bars and dark-on-light panels
            data = tess.image_to_data(img, config="--psm 11", output_type=tess.Output.DICT)
            found += self._parse(data, 30, lambda bx, by, bw, bh: (x0 + bx / scale, y0 + by / scale,
                                                                   bw / scale, bh / scale))
        self._words[region] = found
        return found

    @staticmethod
    def _parse(data, min_conf, to_client):
        out = []
        for i, text in enumerate(data["text"]):
            text = (text or "").strip()
            conf = float(data["conf"][i]) if str(data["conf"][i]) not in ("", "-1") else -1.0
            if _norm(text) and conf >= min_conf:
                out.append((text, conf, to_client(data["left"][i], data["top"][i], data["width"][i], data["height"][i])))
        return out

    def _line_boxes(self, region):
        """Boxes that look like single lines of text (gradient + horizontal
        closing), in the prepared crop's pixels."""
        import cv2
        gray, scale, _x0, _y0 = self._prepared(region)
        h_ui = self.size[1] * scale
        grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        mask = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        joint = max(3, int(h_ui * 0.006))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (joint, 1)))
        # RETR_LIST: a label inside a button outline is its own contour.
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if h_ui * 0.008 <= h <= h_ui * 0.05 and w >= h * 1.5:
                boxes.append((x, y, w, h))
        return gray, scale, boxes

    def read_line(self, gray, box, scale, x0, y0):
        """Words of one text line (psm 7): as is, inverted, then binarized."""
        import cv2
        tess = self._tesseract()
        x, y, w, h = box
        pad = max(2, h // 3)
        left, top = max(0, x - pad), max(0, y - pad)
        crop = gray[top:y + h + pad, left:x + w + pad]
        f = 48.0 / max(1, crop.shape[0])
        crop = cv2.resize(crop, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        otsu = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        # dark-on-light, light-on-dark, then hard black/white (white on red buttons)
        for img in (crop, 255 - crop, 255 - otsu if otsu.mean() < 128 else otsu):
            data = tess.image_to_data(img, config="--psm 7", output_type=tess.Output.DICT)
            got = self._parse(data, 40, lambda bx, by, bw, bh: (x0 + (left + bx / f) / scale,
                                                                y0 + (top + by / f) / scale,
                                                                bw / f / scale, bh / f / scale))
            if got:
                return got
        return []

    def find(self, phrase, region, min_score=0.8, deep=True):
        """Centre (x, y) in client px of `phrase` (one or more words on one
        line, read left to right), or None. Whole-region read first; if that
        misses, read the line-shaped boxes one by one, most phrase-like
        shape first, and stop at the first match (Tesseract misses small
        labels on buttons when it has to segment a whole busy screen)."""
        hit = self._find(phrase, self.words(region), min_score)
        if hit or not deep:
            return hit
        gray, scale, boxes = self._line_boxes(region)
        x0, y0 = int(region[0] * self.size[0]), int(region[1] * self.size[1])
        want = max(1.5, len(phrase) * 0.62)  # width / height of the phrase in this UI font
        boxes.sort(key=lambda b: abs(b[2] / float(b[3]) - want) / want)
        for box in boxes[:30]:
            if abs(box[2] / float(box[3]) - want) / want > 2.0:  # a whole button can hold the label
                break
            hit = self._find(phrase, self.read_line(gray, box, scale, x0, y0), min_score)
            if hit:
                return hit
        return None

    @staticmethod
    def _find(phrase, words, min_score):
        targets = phrase.split()
        best, best_score = None, 0.0
        for i, (text, _conf, box) in enumerate(words):
            score = _similar(text, targets[0])
            if score < min_score:
                continue
            boxes, total = [box], score
            ok = True
            for target in targets[1:]:
                last = boxes[-1]
                line = [(t, b) for t, _c, b in words
                        if abs((b[1] + b[3] / 2) - (last[1] + last[3] / 2)) < max(b[3], last[3]) * 0.6
                        and 0 <= b[0] - (last[0] + last[2]) < max(last[3], b[3]) * 3]
                match = max(line, key=lambda tb: _similar(tb[0], target), default=None)
                if match is None or _similar(match[0], target) < min_score:
                    ok = False
                    break
                boxes.append(match[1])
                total += _similar(match[0], target)
            if not ok:
                continue
            total /= len(targets)
            if total > best_score:
                x0 = min(b[0] for b in boxes)
                y0 = min(b[1] for b in boxes)
                x1 = max(b[0] + b[2] for b in boxes)
                y1 = max(b[1] + b[3] for b in boxes)
                best, best_score = ((x0 + x1) / 2, (y0 + y1) / 2), total
        return best


class PTCGLImporter:
    def __init__(self, text, name=None, status=None, cancel=None, rarest=True):
        self.text = text
        self.name = (name or "").strip()
        self.status = status or (lambda message: None)
        self.cancel = cancel or threading.Event()
        self.rarest = rarest
        self.hwnd = None

    # ── plumbing ──────────────────────────────────────────────────────────
    def _say(self, message):
        self.status(message)

    def _check(self):
        if user32.GetAsyncKeyState(0x1B) & 0x8000:  # Esc
            self.cancel.set()
        if self.cancel.is_set():
            raise ImportStopped("Stopped.")
        if not self.hwnd or not user32.IsWindow(self.hwnd):
            raise ImportStopped("Pokémon TCG Live closed.")

    def _focus(self):
        if game_window.is_foreground(self.hwnd):
            return True
        if user32.IsIconic(self.hwnd):
            user32.ShowWindow(self.hwnd, 9)  # SW_RESTORE
        user32.keybd_event(0x12, 0, 0, 0)  # Alt lets SetForegroundWindow work
        user32.SetForegroundWindow(self.hwnd)
        user32.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.5)
        return game_window.is_foreground(self.hwnd)

    def _screen(self):
        self._check()
        if not game_window.is_foreground(self.hwnd):
            raise ImportStopped("Stopped: Pokémon TCG Live is no longer in front.")
        return Screen(self.hwnd)

    def _click(self, screen, point):
        self._check()
        if not game_window.is_foreground(self.hwnd):
            raise ImportStopped("Stopped: Pokémon TCG Live is no longer in front.")
        from AutoClicker import AutoClicker
        AutoClicker.physical_click(screen.origin[0] + point[0], screen.origin[1] + point[1])
        time.sleep(0.6)

    def _wait_for(self, phrase, region, timeout=STEP_S, say=None):
        deadline = time.time() + timeout
        while True:
            screen = self._screen()
            point = screen.find(phrase, region)
            if point:
                return screen, point
            if time.time() > deadline:
                raise ImportStopped(say or f"Couldn't find \"{phrase.title()}\" in Pokémon TCG Live.")
            time.sleep(0.6)

    # ── steps ─────────────────────────────────────────────────────────────
    def _open_decks(self):
        """To the Decks screen, waiting while the main menu isn't showing."""
        deadline = time.time() + WAIT_MENU_S
        told = False
        while True:
            screen = self._screen()
            if screen.find("CREATE A DECK", DECK_GRID, deep=False):
                return
            if screen.find("WANT TO EXIT", DIALOG, deep=False):
                # Leaving a deck that isn't valid (e.g. cards you don't own) asks
                # first; the deck stays saved either way.
                exit_button = screen.find("EXIT", (0.5, 0.6, 0.65, 0.9))
                if exit_button:
                    self._click(screen, exit_button)
                    time.sleep(1.0)
                    continue
            library = screen.find("CARD LIBRARY", EDITOR, deep=False)
            if library:
                # Inside a deck: the DECKS tab doesn't leave it; the back
                # arrow left of "Card Library" does (offset scales with height).
                self._say("Leaving the deck editor…")
                self._click(screen, (max(4, library[0] - 0.145 * screen.size[1]), library[1]))
                time.sleep(1.0)
                continue
            nav = screen.find("DECKS", NAV, deep=False)
            if nav:
                self._say("Opening Decks…")
                self._click(screen, nav)
                try:
                    self._wait_for("CREATE A DECK", DECK_GRID, timeout=8)
                    return
                except ImportStopped:
                    screen = self._screen()
                    recents = screen.find("RECENTS", DECK_GRID)
                    if recents:
                        self._click(screen, recents)
                        self._wait_for("CREATE A DECK", DECK_GRID, timeout=6)
                        return
                    raise
            if time.time() > deadline:
                raise ImportStopped("The main menu never showed up (finish your match, then try again).")
            if not told:
                self._say("Waiting for Pokémon TCG Live's main menu…")
                told = True
            time.sleep(1.5)

    def _choose_rarest(self, screen, settings):
        """Set Import settings to Rarest owned (the dropdown right of its label)."""
        h = screen.size[1]
        # The dropdown sits right of the label, on the same row.
        band = (settings[0] / screen.size[0], (settings[1] - 0.03 * h) / h,
                min(1.0, (settings[0] + 0.5 * h) / screen.size[0]), (settings[1] + 0.03 * h) / h)
        if screen.find("RAREST OWNED", band):
            return
        current = screen.find("DIRECT", band) or screen.find("OWNED", band)
        if not current:
            raise ImportStopped("Couldn't find the Import settings menu.")
        self._click(screen, current)
        screen, option = self._wait_for("RAREST OWNED", DIALOG)
        self._click(screen, option)
        screen, confirm = self._wait_for("CONFIRM", DIALOG)
        self._click(screen, confirm)
        self._wait_for("IMPORT SETTINGS", DIALOG)

    def _put_clipboard(self):
        import win32clipboard
        for _attempt in range(5):
            try:
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardText(self.text, win32clipboard.CF_UNICODETEXT)
                finally:
                    win32clipboard.CloseClipboard()
                return
            except Exception:
                time.sleep(0.2)
        raise ImportStopped("Couldn't put the list on the clipboard.")

    def _type(self, text):
        """Unicode keystrokes (SendInput), so names with accents type right."""
        from ctypes import wintypes

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        for ch in text:
            for flags in (0x0004, 0x0004 | 0x0002):  # KEYEVENTF_UNICODE, + KEYUP
                inp = INPUT(type=1)
                inp.ki = KEYBDINPUT(0, ord(ch), flags, 0, None)
                user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.02)

    def _key(self, vk, times=1):
        for _ in range(times):
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 2, 0)
            time.sleep(0.015)

    def _rename(self):
        screen, title = self._wait_for("NEW DECK", RIGHT_PANEL, timeout=6,
                                       say="The deck was imported but I couldn't find it to rename it.")
        # The edit (pencil) button sits at the right end of the deck's title bar;
        # PTCGL sizes its UI by window height, so its offset scales with it.
        w, h = screen.size
        self._click(screen, (w - 0.071 * h, title[1]))
        screen, _heading = self._wait_for("SET DECK NAME", RIGHT_PANEL, timeout=5,
                                          say="The deck was imported; renaming didn't open, so it keeps PTCGL's name.")
        field = screen.find("NEW DECK", RIGHT_PANEL) or (w - 0.55 * h, _heading[1] + 0.07 * h)
        self._click(screen, field)
        self._key(0x23)        # End
        self._key(0x08, 40)    # Backspace the old name
        self._type(self.name[:30])
        screen, done = self._wait_for("DONE", RIGHT_PANEL)
        self._click(screen, done)

    # ── run ───────────────────────────────────────────────────────────────
    def run(self):
        """(ok, message). Never raises."""
        try:
            self.hwnd = game_window.find_game_hwnd()
            if not self.hwnd:
                return False, "Pokémon TCG Live isn't running."
            request_minimize_dashboard()
            time.sleep(1.2)  # the overlay polls once a second
            if not self._focus():
                return False, "Couldn't bring Pokémon TCG Live to the front."
            self._open_decks()
            self._say("Creating the deck…")
            screen, tile = self._wait_for("CREATE A DECK", DECK_GRID)
            self._click(screen, tile)
            screen, settings = self._wait_for("IMPORT SETTINGS", DIALOG)
            if self.rarest:
                self._say("Choosing your rarest cards…")
                self._choose_rarest(screen, settings)
            self._put_clipboard()
            screen, button = self._wait_for("FROM YOUR CLIPBOARD", DIALOG)
            self._say("Importing…")
            self._click(screen, button)
            self._wait_for("CARD LIBRARY", EDITOR, timeout=STEP_S,
                           say="Pokémon TCG Live didn't accept the list.")
            if self.name:
                self._say("Naming the deck…")
                self._rename()
            return True, "Imported into Pokémon TCG Live" + (f" as {self.name}." if self.name else ".")
        except ImportStopped as exc:
            return False, str(exc)
        except Exception as exc:  # never leave the user without an answer
            return False, f"Import failed: {exc}"
