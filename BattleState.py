"""
Battle-State Detector for Pokemon TCG Live

Detects whether the game is showing the in-battle HUD by sampling three
color-signature regions (resolution-independent, relative to the game
window rect):

  1. Chat bubble   — white circle on the left edge (~59% height)
  2. Prize counter — yellow badge on the left deck box (bottom-left)
  3. Timer strip   — dark HUD panel on the right edge with clock text

When the HUD disappears (battle over), the monitor immediately starts
polling for the BATTLE LOG button and shows the Continue blocker.

All checks are cheap (a handful of 1px samples via mss) so this can poll
at a low interval without measurable CPU cost.
"""

import os
import time

import mss
import numpy as np
import win32gui

from RankDetector import RankDetector

# How many of the three HUD checks must pass to call it "in battle".
REQUIRED_HITS = 2

# Poll interval (seconds) while in battle, watching for HUD to vanish.
IN_BATTLE_POLL = 2.0

# After HUD disappears, how long to keep confirming it's really gone
# before declaring battle end (avoids HUD flicker on transitions).
HUD_GONE_CONFIRMATIONS = 2
HUD_GONE_CONFIRM_DELAY = 0.5


def _sample_region(img, x, y, half=3):
    """Mean BGR of a small box around relative (x, y) in image `img`
    (numpy HxWx3). Returns (B, G, R) floats."""
    h, w = img.shape[:2]
    cx, cy = int(w * x), int(h * y)
    x0, x1 = max(cx - half, 0), min(cx + half, w)
    y0, y1 = max(cy - half, 0), min(cy + half, h)
    patch = img[y0:y1, x0:x1]
    if patch.size == 0:
        return (0.0, 0.0, 0.0)
    return tuple(float(c) for c in patch.reshape(-1, 3).mean(axis=0))


def _is_whiteish(bgr, min_level=200):
    b, g, r = bgr
    return min(b, g, r) >= min_level


def _is_yellowish(bgr):
    b, g, r = bgr
    return r > 150 and g > 120 and b < 110 and (r - b) > 60


def _is_dark_panel(bgr, max_level=70):
    b, g, r = bgr
    return max(b, g, r) <= max_level


def check_hud(game_rect=None, sct=None):
    """Return (in_battle, hits, details).

    Samples the three HUD anchors and reports which passed. Coordinates
    are relative fractions tuned from a 1366x768 reference screenshot and
    scale with the live window rect.
    """
    try:
        if game_rect is None:
            gw = RankDetector().find_game_window()
            if not gw:
                return False, 0, ["no_window"]
            l, t = gw["left"], gw["top"]
            w, h = gw["width"], gw["height"]
        else:
            l, t, w, h = game_rect

        with mss.mss() as own_sct:
            sct = own_sct
            shot = sct.grab({"left": l, "top": t, "width": w, "height": h})
        img = np.asarray(shot)[:, :, :3]  # BGRA -> BGR

        hits = 0
        details = []

        # 1) Chat bubble: white circle on the left edge (~59% height).
        chat = _sample_region(img, 0.022, 0.59)
        chat_ok = _is_whiteish(chat, 190)
        hits += chat_ok
        details.append(f"chat={tuple(int(v) for v in chat)}:{'Y' if chat_ok else 'N'}")

        # 2) Prize counter badge (yellow) bottom-left deck box (~86% height).
        prize = _sample_region(img, 0.225, 0.862)
        prize_ok = _is_yellowish(prize)
        hits += prize_ok
        details.append(f"prize={tuple(int(v) for v in prize)}:{'Y' if prize_ok else 'N'}")

        # 3) Timer/HUD strip: dark panel on the right edge (~30% height).
        timer = _sample_region(img, 0.975, 0.30)
        timer_ok = _is_dark_panel(timer)
        hits += timer_ok
        details.append(f"timer={tuple(int(v) for v in timer)}:{'Y' if timer_ok else 'N'}")

        return hits >= REQUIRED_HITS, hits, details
    except Exception as exc:
        return False, 0, [f"error:{exc}"]


def wait_for_battle_end(on_battle_active=None, poll_interval=IN_BATTLE_POLL,
                        log_fn=print, stop_check=None):
    """Block until the in-battle HUD appears and then disappears.

    Returns True if a battle end was observed, False if stop_check() became
    True first (or the game window vanished for good).
    """
    was_in_battle = False
    while True:
        if stop_check is not None and stop_check():
            return False
        in_battle, hits, details = check_hud()
        if in_battle and not was_in_battle:
            log_fn(f"[BattleState] Battle HUD detected ({hits}/3): {', '.join(details)}")
            was_in_battle = True
        elif was_in_battle and not in_battle:
            log_fn(f"[BattleState] Battle HUD gone — battle over ({hits}/3): {', '.join(details)}")
            return True
        elif not was_in_battle:
            # Not in battle: idle poll slowly.
            time.sleep(poll_interval)
        else:
            # In battle: HUD still present, keep watching.
            time.sleep(poll_interval)


if __name__ == "__main__":
    # Standalone test: print HUD state every 2 seconds.
    import sys
    print("Battle-state detector test — Ctrl+C to stop")
    while True:
        in_battle, hits, details = check_hud()
        state = "IN BATTLE" if in_battle else "not in battle"
        print(f"[{time.strftime('%H:%M:%S')}] {state} ({hits}/3): {', '.join(details)}")
        if "--once" in sys.argv:
            break
        time.sleep(2)
