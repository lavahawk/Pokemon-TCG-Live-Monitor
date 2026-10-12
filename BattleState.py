"""
Battle-state (in-battle HUD) detector for Pokemon TCG Live.

In battle, the game shows a settings gear in the top-right corner of the
board (the menus show a "more" button there instead). This module
template-matches that gear in a small top-right region of the game window.

v2.4.1: replaces the old three-colour-patch check, whose anchors no longer
matched the game's layout (it reported "in battle" on the home screen and
"not in battle" during real matches). Template captured at a 1136 px tall
client area; scaled to the current window height.

The HUD is only a hint (polling speed, re-arming after an end screen); it
never triggers clicks by itself.

Standalone test:  python BattleState.py [--once]
"""

import os
import time

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEAR_TEMPLATE = os.path.join(BASE_DIR, "button_templates", "battle_hud_gear.png")
GEAR_CAPTURE_HEIGHT = 1136
# Search area as fractions of the game window (gear centre is at ~0.969, 0.086).
REGION = (0.90, 0.0, 1.0, 0.18)   # x0, y0, x1, y1
THRESHOLD = 0.80
IN_BATTLE_POLL = 1.5

_template = None
_scaled = {}


def _gear(height):
    """Gear template (gray) scaled for a window of the given height."""
    global _template
    if _template is None:
        _template = cv2.imread(GEAR_TEMPLATE, cv2.IMREAD_GRAYSCALE)
        if _template is None:
            raise FileNotFoundError(GEAR_TEMPLATE)
    key = int(height)
    if key not in _scaled:
        s = height / float(GEAR_CAPTURE_HEIGHT)
        size = max(10, int(round(_template.shape[0] * s)))
        _scaled.clear()
        _scaled[key] = cv2.resize(_template, (size, size), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    return _scaled[key]


def check_hud(game_rect=None, sct=None):
    """Return (in_battle, score_pct, details).

    game_rect: dict {left, top, width, height} or legacy (l, t, w, h) tuple.
    sct:       an mss instance owned by the calling thread (optional).
    """
    try:
        if game_rect is None:
            from game_window import game_rect as _find_rect
            game_rect = _find_rect()
            if not game_rect:
                return False, 0, ["no_window"]
        if isinstance(game_rect, (tuple, list)):
            l, t, w, h = game_rect
            game_rect = {"left": l, "top": t, "width": w, "height": h}
        w, h = game_rect["width"], game_rect["height"]
        x0, y0, x1, y1 = REGION
        box = {"left": game_rect["left"] + int(w * x0), "top": game_rect["top"] + int(h * y0),
               "width": max(1, int(w * (x1 - x0))), "height": max(1, int(h * (y1 - y0)))}
        own = None
        if sct is None:
            import mss
            own = sct = mss.mss()
        try:
            frame = np.asarray(sct.grab(box))
        finally:
            if own is not None:
                own.close()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        tpl = _gear(h)
        if tpl.shape[0] > gray.shape[0] or tpl.shape[1] > gray.shape[1]:
            return False, 0, ["window_too_small"]
        score = float(cv2.minMaxLoc(cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED))[1])
        return score >= THRESHOLD, int(score * 100), [f"gear={score:.2f}"]
    except Exception as exc:
        return False, 0, [f"error:{exc}"]


if __name__ == "__main__":
    import sys
    print("Battle-state detector test - Ctrl+C to stop")
    while True:
        in_battle, score, details = check_hud()
        state = "IN BATTLE" if in_battle else "not in battle"
        print(f"[{time.strftime('%H:%M:%S')}] {state}: {', '.join(details)}")
        if "--once" in sys.argv:
            break
        time.sleep(2)
