"""
Template matcher + Unity-safe physical clicker for Pokemon TCG Live.

What changed in v2.4 (see DevVault -> BUG-010/012/014):
* Multi-scale, grayscale, downscaled matching. Templates captured at one
  window size now match at others (the old exact-pixel matcher missed the
  BATTLE LOG button whenever the window size/DPI differed from capture time).
  The best scale per (template, window height) is cached on disk.
* No pyautogui dependency: clicks use SetCursorPos + mouse_event via ctypes.
* No long-lived mss instance (GDI handle leak). Callers pass in frames, or
  find_on_screen() opens a short-lived mss for one capture.
* Clicks are refused unless the game window is in the foreground, so the
  clicker can never click into another application.

Hard-won timing lesson kept from v2.3: Unity processes a UI click one frame
after mouse-up, so the cursor must stay put ~250 ms before being restored.
"""

import json
import os
import time

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "button_templates")
TEMPLATE_META_FILE = os.path.join(TEMPLATES_DIR, "templates.json")
SCALE_CACHE_FILE = os.path.join(TEMPLATES_DIR, "scale_cache.json")

# Matching works on a frame whose game-window height is normalised to this
# many pixels. Big enough for the 48x52 export icon to stay recognisable,
# small enough that a full multi-scale sweep costs a few milliseconds.
WORK_HEIGHT = 540
DEFAULT_THRESHOLD = 0.82
FULL_SWEEP_EVERY = 6
FULL_SWEEP = [round(s, 3) for s in np.arange(0.45, 1.65, 0.05)]


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def to_gray(frame):
    """BGRA/BGR/gray ndarray -> gray uint8."""
    if frame.ndim == 2:
        return frame
    if frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


class AutoClicker:
    """Finds button templates in game-window frames and clicks them."""

    def __init__(self, game_window=None):
        # game_window kept for backwards compatibility with old callers.
        self.game_window = game_window
        self.templates = {}
        self.meta = _load_json(TEMPLATE_META_FILE)
        self.scale_cache = _load_json(SCALE_CACHE_FILE)
        self.last_score = {}
        self.last_rejected = {}   # name -> (score, x, y) of the last match that failed verify
        self._sweep_counter = {}
        self._tpl_cache = {}      # (name, w, h) -> resized template
        self._loc_cache = {}      # (name, window_height) -> (cx_rel, cy_rel) in window-relative fractions
        self._roi_calls = {}
        os.makedirs(TEMPLATES_DIR, exist_ok=True)

    # ── templates ──────────────────────────────────────────────────────
    def load_template(self, template_name, threshold=DEFAULT_THRESHOLD):
        path = os.path.join(TEMPLATES_DIR, f"{template_name}.png")
        if not os.path.exists(path):
            return False
        image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            return False
        meta = self.meta.get(template_name, {}) if isinstance(self.meta, dict) else {}
        self.templates[template_name] = {
            "image": image,
            "threshold": float(meta.get("threshold", threshold)),
            "capture_height": int(meta.get("window_height") or 0),
        }
        return True

    # ── matching ───────────────────────────────────────────────────────
    def _candidate_scales(self, name, window_height):
        key = f"{name}@{int(window_height)}"
        cached = self.scale_cache.get(key)
        if isinstance(cached, (int, float)) and cached:
            return [cached * 0.95, cached, cached * 1.05], key
        capture_h = self.templates[name]["capture_height"]
        if capture_h:
            s0 = window_height / float(capture_h)
            return [s0 * 0.9, s0 * 0.95, s0, s0 * 1.05, s0 * 1.1], key
        # Unknown capture size: try ~1.0 cheaply, and do the full multi-scale
        # sweep only on every FULL_SWEEP_EVERY-th call until a scale is cached.
        count = self._sweep_counter.get(name, 0) + 1
        self._sweep_counter[name] = count
        if count % FULL_SWEEP_EVERY == 1:
            return list(FULL_SWEEP), key
        return [0.9, 1.0, 1.1], key

    def _resized_template(self, name, tw, th, t_scale):
        key = (name, tw, th)
        img = self._tpl_cache.get(key)
        if img is None:
            src = self.templates[name]["image"]
            img = cv2.resize(src, (tw, th), interpolation=cv2.INTER_AREA if t_scale < 1 else cv2.INTER_LINEAR)
            if len(self._tpl_cache) > 64:
                self._tpl_cache.clear()
            self._tpl_cache[key] = img
        return img

    def _match(self, name, small, scales, factor):
        best = (-1.0, None, None, None)
        for scale in scales:
            t_scale = scale * factor
            th = int(round(self.templates[name]["image"].shape[0] * t_scale))
            tw = int(round(self.templates[name]["image"].shape[1] * t_scale))
            if th < 8 or tw < 8 or th > small.shape[0] or tw > small.shape[1]:
                continue
            t_img = self._resized_template(name, tw, th, t_scale)
            result = cv2.matchTemplate(small, t_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best[0]:
                best = (max_val, scale, max_loc, (tw, th))
        return best

    def next_search_box(self, name, window_height, frame_w, frame_h):
        """(x0, y0, x1, y1) of the frame the next find_in_frame call will
        read, or None when it searches the whole frame. Lets a caller grab
        only that area (a full grab costs ~25 ms, the box ~1 ms)."""
        tpl = self.templates.get(name)
        if tpl is None:
            return None
        roi_key = (name, int(window_height), frame_w, frame_h)
        roi = self._loc_cache.get(roi_key)
        if roi is None:
            saved = self.scale_cache.get(f"roi:{name}@{int(window_height)}@{frame_w}x{frame_h}")
            if isinstance(saved, list) and len(saved) == 2:
                roi = (saved[0] * frame_w, saved[1] * frame_h)
        if roi is None or (self._roi_calls.get(roi_key, 0) + 1) % 8 == 0:
            return None
        cx, cy = roi
        grow = 1.6 * (window_height / max(1, tpl["capture_height"] or window_height))
        pad_x = int(tpl["image"].shape[1] * grow)
        pad_y = int(tpl["image"].shape[0] * grow)
        x0, y0 = max(0, int(cx - pad_x)), max(0, int(cy - pad_y))
        x1, y1 = min(frame_w, int(cx + pad_x)), min(frame_h, int(cy + pad_y))
        return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None

    def find_in_frame(self, name, frame, origin, window_height, window_origin=None, verify=None):
        """Find a template in a captured frame.

        frame          ndarray (BGRA/BGR/gray) of the searched region
        origin         (left, top) screen coords of the frame's top-left
        window_height  current game-window height in physical pixels
        verify         optional fn(gray_crop_of_match) -> bool; a match that
                       fails it is rejected and its position is not cached
        Returns (x, y, score) screen-centre coords or None.

        Speed: after the first hit the button's position (relative to the
        frame) is remembered and only a small area around it is searched;
        a full-frame search still runs every 8th call as a safety net.
        """
        tpl = self.templates.get(name)
        if tpl is None or frame is None or frame.size == 0 or window_height <= 0:
            return None
        gray = to_gray(frame)
        factor = min(1.0, WORK_HEIGHT / float(window_height))
        scales, cache_key = self._candidate_scales(name, window_height)

        roi_key = (name, int(window_height), gray.shape[1], gray.shape[0])
        box = self.next_search_box(name, window_height, gray.shape[1], gray.shape[0])
        self._roi_calls[roi_key] = self._roi_calls.get(roi_key, 0) + 1
        best = (-1.0, None, None, None)
        offset = (0, 0)
        if box is not None:
            x0, y0, x1, y1 = box
            sub = gray[y0:y1, x0:x1]
            if sub.size:
                small = cv2.resize(sub, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA) if factor < 1.0 else sub
                best = self._match(name, small, scales[:3] if len(scales) > 3 else scales, factor)
                offset = (x0, y0)
            if best[0] < tpl["threshold"]:
                # The button always appears in the same spot, so a miss in
                # the remembered area means "not on screen" - skip the
                # expensive full search (it still runs every 8th call).
                self.last_score[name] = best[0]
                return None
        if best[2] is None:
            small = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA) if factor < 1.0 else gray
            best = self._match(name, small, scales, factor)
            offset = (0, 0)

        score, scale, loc, size = best
        self.last_score[name] = score
        if loc is None or score < tpl["threshold"]:
            if cache_key in self.scale_cache and score < tpl["threshold"] * 0.85:
                self.scale_cache.pop(cache_key, None)
            return None
        fx = offset[0] + (loc[0] + size[0] / 2.0) / factor
        fy = offset[1] + (loc[1] + size[1] / 2.0) / factor
        if verify is not None:
            # Template scores alone are not proof (a dark bar with light text
            # on the home screen scored 0.84 for BATTLE LOG). Check the
            # matched box itself, and never cache an unverified position.
            bw, bh = size[0] / factor, size[1] / factor
            x0, y0 = max(0, int(fx - bw / 2)), max(0, int(fy - bh / 2))
            x1, y1 = min(gray.shape[1], int(fx + bw / 2)), min(gray.shape[0], int(fy + bh / 2))
            crop = gray[y0:y1, x0:x1]
            if crop.size == 0 or not verify(crop):
                self.last_rejected[name] = (round(float(score), 2), int(round(origin[0] + fx)), int(round(origin[1] + fy)))
                if self._loc_cache.get(roi_key) is not None:
                    self._loc_cache.pop(roi_key, None)
                self.scale_cache.pop(f"roi:{name}@{int(window_height)}@{gray.shape[1]}x{gray.shape[0]}", None)
                return None
        if self.scale_cache.get(cache_key) != scale:
            self.scale_cache[cache_key] = scale
            _save_json(SCALE_CACHE_FILE, self.scale_cache)
        if roi_key not in self._loc_cache:
            self.scale_cache[f"roi:{name}@{int(window_height)}@{gray.shape[1]}x{gray.shape[0]}"] = [
                round(fx / gray.shape[1], 4), round(fy / gray.shape[0], 4)]
            _save_json(SCALE_CACHE_FILE, self.scale_cache)
        self._loc_cache[roi_key] = (fx, fy)
        return int(round(origin[0] + fx)), int(round(origin[1] + fy)), float(score)

    def find_on_screen(self, name, region, window_height):
        """One-shot capture + match. region = {left, top, width, height}."""
        import mss
        with mss.mss() as sct:
            shot = np.asarray(sct.grab(region))
        return self.find_in_frame(name, shot, (region["left"], region["top"]), window_height)

    # Backwards-compatible API used by older scripts.
    def find_button(self, template_name, region=None):
        region = region or self.game_window
        if not region:
            return None
        height = (self.game_window or region).get("height", region["height"])
        hit = self.find_on_screen(template_name, region, height)
        return (hit[0], hit[1]) if hit else None

    # ── clicking ───────────────────────────────────────────────────────
    @staticmethod
    def physical_click(x, y, restore=True):
        """Real cursor click with Unity-safe timing that survives the user
        moving the mouse meanwhile.

        * The cursor is pinned to the target with ClipCursor for the whole
          down/up/settle window, so a moving mouse can't drag it off.
        * Down and up are sent as absolute-position events (the position
          travels with the event), and the position is re-asserted first.
        * If the user is holding the left button (dragging), wait for the
          release (up to 1.5 s) instead of injecting a click mid-drag.
        """
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        MOVE, LEFTDOWN, LEFTUP = 0x0001, 0x0002, 0x0004
        ABSOLUTE, VIRTUALDESK = 0x8000, 0x4000
        x, y = int(x), int(y)

        saved = wintypes.POINT()
        have_saved = bool(user32.GetCursorPos(ctypes.byref(saved)))

        deadline = time.time() + 1.5
        while user32.GetAsyncKeyState(0x01) & 0x8000 and time.time() < deadline:
            time.sleep(0.02)

        # Absolute coordinates are normalised over the virtual desktop.
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        vw, vh = max(2, user32.GetSystemMetrics(78)), max(2, user32.GetSystemMetrics(79))
        nx = int(round((x - vx) * 65535 / (vw - 1)))
        ny = int(round((y - vy) * 65535 / (vh - 1)))

        def press(flag):
            user32.SetCursorPos(x, y)
            user32.mouse_event(MOVE | ABSOLUTE | VIRTUALDESK | flag, nx, ny, 0, 0)

        clip = wintypes.RECT(x, y, x + 1, y + 1)
        try:
            user32.SetCursorPos(x, y)
            user32.ClipCursor(ctypes.byref(clip))
            time.sleep(0.08)
            press(LEFTDOWN)
            time.sleep(0.06)
            press(LEFTUP)
            time.sleep(0.25)  # Unity reads the click a frame after mouse-up
        finally:
            user32.ClipCursor(None)
            if restore and have_saved:
                user32.SetCursorPos(saved.x, saved.y)
        return True


def save_template_meta(template_name, window_rect, threshold=DEFAULT_THRESHOLD):
    """Record the game-window size a template was captured at (used for scaling)."""
    meta = _load_json(TEMPLATE_META_FILE)
    meta[template_name] = {
        "window_width": int(window_rect.get("width", 0)) if window_rect else 0,
        "window_height": int(window_rect.get("height", 0)) if window_rect else 0,
        "threshold": threshold,
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_json(TEMPLATE_META_FILE, meta)
    # Old scale guesses are invalid for a new template.
    cache = _load_json(SCALE_CACHE_FILE)
    cache = {k: v for k, v in cache.items()
             if not k.startswith(f"{template_name}@") and not k.startswith(f"roi:{template_name}@")}
    _save_json(SCALE_CACHE_FILE, cache)
