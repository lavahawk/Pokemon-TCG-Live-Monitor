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
# Search area as fractions of the game window. Gear centre: ~0.969, 0.086
# before the Nov 2026 update; since then ~0.988, 0.021 (a small dark tab in
# the very corner) and smaller.
REGION = (0.90, 0.0, 1.0, 0.18)   # x0, y0, x1, y1
# Gear side as a fraction of the window height: the original capture (36 px
# at 1136), and the Nov 2026 layout (16 px at 720; 15/17 px scored 0.81/0.84,
# so it is also tried a few percent either side).
GEAR_HEIGHT_FRACTIONS = (36 / 1136.0, 16 / 720.0 * 0.94, 16 / 720.0, 16 / 720.0 * 1.06)
THRESHOLD = 0.80
IN_BATTLE_POLL = 1.5

_template = None
_scaled = {}


def _gear(height):
    """Gear templates (gray), one per known gear size, for a window of the given height."""
    global _template
    if _template is None:
        _template = cv2.imread(GEAR_TEMPLATE, cv2.IMREAD_GRAYSCALE)
        if _template is None:
            raise FileNotFoundError(GEAR_TEMPLATE)
    key = int(height)
    if key not in _scaled:
        _scaled.clear()
        sizes = sorted({max(10, int(round(height * f))) for f in GEAR_HEIGHT_FRACTIONS})
        _scaled[key] = [cv2.resize(_template, (n, n), interpolation=cv2.INTER_AREA
                                   if n < _template.shape[0] else cv2.INTER_LINEAR) for n in sizes]
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
        tpls = [t for t in _gear(h) if t.shape[0] <= gray.shape[0] and t.shape[1] <= gray.shape[1]]
        if not tpls:
            return False, 0, ["window_too_small"]
        score = max(float(cv2.minMaxLoc(cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED))[1]) for t in tpls)
        import ocr_debug
        ocr_debug.report("HUD gear", box, hit=score >= THRESHOLD, score=score)
        return score >= THRESHOLD, int(score * 100), [f"gear={score:.2f}"]
    except Exception as exc:
        return False, 0, [f"error:{exc}"]


# ── staged battle-end signals (Nov 2026 layout) ─────────────────────────
# The end of a battle runs: board (emote buttons left, prize counters right)
# -> prize star / GG (both gone) -> an all-white flash -> the end screen with
# BATTLE LOG. Measured on 720p frames, checked at 720/1136/1440.
EMOTES_TEMPLATE = os.path.join(BASE_DIR, "button_templates", "battle_emotes.png")
EMOTES_CAPTURE_HEIGHT = 720
EMOTES_REGION = (0.0, 0.45, 0.10, 0.68)    # x0, y0, x1, y1 (window fractions)
EMOTES_THRESHOLD = 0.70                     # board 0.98-1.00, other screens <= 0.33
# Prize counters: a red box above a blue box at the right edge.
COUNTERS_REGION = (0.94, 0.30, 1.0, 0.60)
COUNTER_MIN_AREA = 250 / (720.0 * 720.0)    # per box, as a share of height^2
# White flash: a band across the middle of the window, nearly all white.
WHITE_REGION = (0.20, 0.40, 0.80, 0.60)
WHITE_MIN_SHARE = 0.95

_emotes = None
_emotes_scaled = {}


def _box(game_rect, region):
    w, h = game_rect["width"], game_rect["height"]
    x0, y0, x1, y1 = region
    return {"left": game_rect["left"] + int(w * x0), "top": game_rect["top"] + int(h * y0),
            "width": max(1, int(w * (x1 - x0))), "height": max(1, int(h * (y1 - y0)))}


def _emotes_template(height):
    global _emotes
    if _emotes is None:
        _emotes = cv2.imread(EMOTES_TEMPLATE, cv2.IMREAD_GRAYSCALE)
        if _emotes is None:
            raise FileNotFoundError(EMOTES_TEMPLATE)
    key = int(height)
    if key not in _emotes_scaled:
        s = height / float(EMOTES_CAPTURE_HEIGHT)
        _emotes_scaled.clear()
        _emotes_scaled[key] = cv2.resize(_emotes, None, fx=s, fy=s,
                                         interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    return _emotes_scaled[key]


def emotes_score(frame_bgra, height):
    gray = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2GRAY)
    tpl = _emotes_template(height)
    if tpl.shape[0] > gray.shape[0] or tpl.shape[1] > gray.shape[1]:
        return 0.0
    return float(cv2.minMaxLoc(cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED))[1])


def counters_visible(frame_bgra, height):
    """True when a solid red box sits directly above a solid blue box."""
    px = frame_bgra[:, :, :3].astype(np.int16)
    b, g, r = px[:, :, 0], px[:, :, 1], px[:, :, 2]
    min_area = COUNTER_MIN_AREA * height * height

    def biggest(mask):
        n, _l, stats, cents = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
        if n <= 1:
            return None
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        return cents[i] if stats[i, cv2.CC_STAT_AREA] >= min_area else None

    red = biggest((r - g > 60) & (r - b > 60))
    blue = biggest((b - r > 50) & (b - g > 15))
    if red is None or blue is None:
        return False
    return red[1] < blue[1] and abs(red[0] - blue[0]) < 0.06 * height


def white_share(frame_bgra):
    return float((frame_bgra[:, :, :3].min(axis=2) > 235).mean())


def battle_signals(game_rect, sct):
    """{'emotes': bool, 'counters': bool, 'details': str} for the board's
    left and right HUD; both gone means the battle is ending."""
    h = game_rect["height"]
    emotes = float(emotes_score(np.asarray(sct.grab(_box(game_rect, EMOTES_REGION))), h))
    counters = counters_visible(np.asarray(sct.grab(_box(game_rect, COUNTERS_REGION))), h)
    return {"emotes": emotes >= EMOTES_THRESHOLD, "counters": counters,
            "details": f"emotes={emotes:.2f} counters={'yes' if counters else 'no'}"}


def white_flash(game_rect, sct):
    """True on the all-white frame between GG and the end screen."""
    return white_share(np.asarray(sct.grab(_box(game_rect, WHITE_REGION)))) >= WHITE_MIN_SHARE


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
