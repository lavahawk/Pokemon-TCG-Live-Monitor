"""
OCR Bounding Box Debug (Settings). Every screen check reports the box it
read, and debug_overlay.py draws those boxes over the game in real time;
the battle-end watcher also records the end-of-battle sequence (see
EndScreenRecorder) for building new detectors.

Each process writes Logs/.ocr_debug_<pid>.json (at most every 100 ms, only
while debug mode is on); the overlay merges the files that are fresh. Off,
report() costs one dict lookup.
"""

import json
import os
import shutil
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "Logs")
PREFIX = ".ocr_debug_"
END_SCREEN_DIR = os.path.join(LOG_DIR, "end_screens")
WRITE_EVERY_S = 0.1
SETTING_EVERY_S = 3.0
KEEP_S = 2.5  # the overlay fades a box out when it was not checked again within this

_lock = threading.Lock()
_boxes = {}
_state = {"on": False, "checked": 0.0, "written": 0.0, "pending": False}


def enabled():
    now = time.time()
    if now - _state["checked"] > SETTING_EVERY_S:
        try:
            from app_settings import load_app_settings
            _state["on"] = bool(load_app_settings().get("debug_mode", False))
        except Exception:
            _state["on"] = False
        _state["checked"] = now
    return _state["on"]


def debug_file(pid=None):
    return os.path.join(LOG_DIR, f"{PREFIX}{pid or os.getpid()}.json")


def report(name, box, hit=None, score=None, text=None):
    """A screen check just read `box` ({left, top, width, height}, physical
    screen pixels). hit: the check found what it looks for; text: what OCR read."""
    if not box or not enabled():
        return
    entry = {"x": int(box["left"]), "y": int(box["top"]), "w": int(box["width"]),
             "h": int(box["height"]), "t": time.time()}
    if hit is not None:
        entry["hit"] = bool(hit)
    if score is not None:
        entry["score"] = round(float(score), 2)
    if text is not None:
        entry["text"] = " ".join(str(text).split())[:60]
    with _lock:
        old = _boxes.get(name)
        if text is None and old and "text" in old and (old["x"], old["y"]) == (entry["x"], entry["y"]):
            entry["text"] = old["text"]  # a re-capture keeps the last reading
        _boxes[name] = entry
        due = time.time() - _state["written"] >= WRITE_EVERY_S
        if not due and not _state["pending"]:
            _state["pending"] = True
            timer = threading.Timer(WRITE_EVERY_S, _flush)
            timer.daemon = True
            timer.start()
    if due:
        _flush()


def _flush():
    with _lock:
        _state["pending"] = False
        _state["written"] = time.time()
        now = time.time()
        for key in [k for k, v in _boxes.items() if now - v["t"] > 30]:
            del _boxes[key]
        data = json.dumps({"pid": os.getpid(), "boxes": _boxes})
    path = debug_file()
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        pass  # the overlay was reading it; the next report writes again


def read_all(now=None):
    """{name: entry} from every process, boxes checked within KEEP_S."""
    now = now or time.time()
    out = {}
    try:
        names = os.listdir(LOG_DIR)
    except Exception:
        return out
    for fname in names:
        if not (fname.startswith(PREFIX) and fname.endswith(".json")):
            continue
        path = os.path.join(LOG_DIR, fname)
        try:
            if now - os.path.getmtime(path) > 120:
                os.remove(path)  # a process that ended
                continue
            with open(path, encoding="utf-8") as f:
                boxes = json.load(f).get("boxes") or {}
        except Exception:
            continue
        for name, entry in boxes.items():
            if now - entry.get("t", 0) <= KEEP_S:
                out[name] = entry
    return out


class EndScreenRecorder:
    """Saves the game window every 0.5 s from the moment the battle HUD goes
    away until shortly after the end screen (Logs/end_screens/<time>/).
    A recording where no end screen followed (the HUD was only covered by
    a deck search or an animation) is deleted; the newest KEEP are kept."""

    EVERY_S = 0.5
    MAX_S = 45
    AFTER_END_S = 3
    KEEP = 5
    WIDTH = 1280

    def __init__(self, log=lambda msg: None):
        self.log = log
        self.dir = None

    def start(self):
        if self.dir is not None:
            return
        self.dir = os.path.join(END_SCREEN_DIR, time.strftime("%Y-%m-%d_%H-%M-%S"))
        self.started = time.time()
        self.next = 0.0
        self.until = self.started + self.MAX_S
        self.ended = False
        self.pending = None

    def end_screen(self, sct, rect):
        """The BATTLE LOG button was confirmed: keep this recording."""
        if self.dir is None:
            return
        self.ended = True
        self.until = time.time() + self.AFTER_END_S
        try:
            # Grabbed now (~25 ms), written on the next tick: encoding a
            # full-size PNG here would delay the export clicks.
            import numpy as np
            self.pending = np.asarray(sct.grab(rect))[:, :, :3].copy()
        except Exception:
            self.pending = None

    def hud_back(self):
        if self.dir is not None and not self.ended:
            self._discard()

    def tick(self, sct, rect):
        if self.dir is None:
            return
        if self.pending is not None:
            self._write("end_screen_full.png", self.pending)
            self.pending = None
        now = time.time()
        if now > self.until:
            if self.ended:
                self.log(f"End screen recorded: {self.dir}")
                self.dir = None
                self._prune()
            else:
                self._discard()
            return
        if now >= self.next:
            self.next = now + self.EVERY_S
            self._save(sct, rect, f"{now - self.started:06.2f}s.jpg")

    def _save(self, sct, rect, name):
        try:
            import cv2
            import numpy as np
            frame = np.asarray(sct.grab(rect))[:, :, :3]
            if frame.shape[1] > self.WIDTH:
                f = self.WIDTH / frame.shape[1]
                frame = cv2.resize(frame, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
            self._write(name, frame)
        except Exception as exc:
            self.log(f"End screen recording failed: {exc}")
            self.dir = None

    def _write(self, name, frame):
        try:
            import cv2
            os.makedirs(self.dir, exist_ok=True)
            cv2.imwrite(os.path.join(self.dir, name), frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 85] if name.endswith(".jpg") else [])
        except Exception as exc:
            self.log(f"End screen recording failed: {exc}")
            self.dir = None

    def _discard(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir = None

    def _prune(self):
        try:
            runs = sorted(d for d in os.listdir(END_SCREEN_DIR)
                          if os.path.isdir(os.path.join(END_SCREEN_DIR, d)))
            for d in runs[:-self.KEEP]:
                shutil.rmtree(os.path.join(END_SCREEN_DIR, d), ignore_errors=True)
        except Exception:
            pass


# ── adjustable OCR boxes (debug overlay, "Edit boxes") ──────────────────
REGIONS_FILE = os.path.join(BASE_DIR, "screen_regions.json")
EDITABLE = ("rank", "my_deck_name", "menu_text")  # read by RankDetector


def load_regions():
    try:
        with open(REGIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def region_box(region, game):
    """A screen_regions.json entry as a physical-pixel box on the game window."""
    if not region or "percent_x" not in region:
        return None
    return {"left": game["left"] + int(game["width"] * region["percent_x"]),
            "top": game["top"] + int(game["height"] * region["percent_y"]),
            "width": int(game["width"] * region["percent_width"]),
            "height": int(game["height"] * region["percent_height"])}


def save_region(name, box, game):
    """Store a dragged box (physical pixels) back as window fractions. The
    first change keeps a copy of the original file next to it."""
    regions = load_regions()
    if name not in regions or not game["width"] or not game["height"]:
        return False
    backup = REGIONS_FILE.replace(".json", ".before_debug.json")
    if not os.path.exists(backup):
        shutil.copyfile(REGIONS_FILE, backup)
    regions[name].update({
        "percent_x": round((box["left"] - game["left"]) / game["width"], 4),
        "percent_y": round((box["top"] - game["top"]) / game["height"], 4),
        "percent_width": round(box["width"] / game["width"], 4),
        "percent_height": round(box["height"] / game["height"], 4),
        "comment": f"Adjusted in OCR Bounding Box Debug at {game['width']}x{game['height']}",
    })
    tmp = REGIONS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(regions, f, indent=2)
    os.replace(tmp, REGIONS_FILE)
    return True
