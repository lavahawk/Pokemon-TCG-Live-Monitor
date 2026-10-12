"""
Battle-state (in-battle HUD) detector for Pokemon TCG Live.

Samples three tiny colour patches (relative to the game window rect):

  1. Chat bubble   - white circle on the left edge (~59% height)
  2. Prize counter - yellow badge on the left deck box (bottom-left)
  3. Timer strip   - dark HUD panel on the right edge

>= 2 of 3 hits means "in battle". The HUD is only a hint used to speed up
the BATTLE LOG button search; it never triggers clicks by itself.

v2.4: only the three 12x12 patches are captured (not the whole window), and
the caller supplies the mss instance + rect, so no GDI objects leak and no
window enumeration happens per poll (BUG-010).

Standalone test:  python BattleState.py [--once]
"""

import time

import numpy as np

REQUIRED_HITS = 2
IN_BATTLE_POLL = 1.5

ANCHORS = {
    "chat": (0.022, 0.59),
    "prize": (0.225, 0.862),
    "timer": (0.975, 0.30),
}
PATCH = 6  # half-size in pixels


def _is_whiteish(bgr, min_level=190):
    b, g, r = bgr
    return min(b, g, r) >= min_level


def _is_yellowish(bgr):
    b, g, r = bgr
    return r > 150 and g > 120 and b < 110 and (r - b) > 60


def _is_dark_panel(bgr, max_level=70):
    return max(bgr) <= max_level


_CHECKS = {"chat": _is_whiteish, "prize": _is_yellowish, "timer": _is_dark_panel}


def _sample(sct, rect, rx, ry):
    cx = rect["left"] + int(rect["width"] * rx)
    cy = rect["top"] + int(rect["height"] * ry)
    box = {"left": cx - PATCH, "top": cy - PATCH, "width": 2 * PATCH, "height": 2 * PATCH}
    patch = np.asarray(sct.grab(box))[:, :, :3]
    return tuple(float(c) for c in patch.reshape(-1, 3).mean(axis=0))


def check_hud(game_rect=None, sct=None):
    """Return (in_battle, hits, details).

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

        own = None
        if sct is None:
            import mss
            own = sct = mss.mss()
        try:
            hits, details = 0, []
            for name, (rx, ry) in ANCHORS.items():
                bgr = _sample(sct, game_rect, rx, ry)
                ok = _CHECKS[name](bgr)
                hits += ok
                details.append(f"{name}={tuple(int(v) for v in bgr)}:{'Y' if ok else 'N'}")
        finally:
            if own is not None:
                own.close()
        return hits >= REQUIRED_HITS, hits, details
    except Exception as exc:
        return False, 0, [f"error:{exc}"]


if __name__ == "__main__":
    import sys
    print("Battle-state detector test - Ctrl+C to stop")
    while True:
        in_battle, hits, details = check_hud()
        state = "IN BATTLE" if in_battle else "not in battle"
        print(f"[{time.strftime('%H:%M:%S')}] {state} ({hits}/3): {', '.join(details)}")
        if "--once" in sys.argv:
            break
        time.sleep(2)
