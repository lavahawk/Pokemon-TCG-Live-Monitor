"""Auto Screenshot (Limitless tab): a picture of the game's end screen after
each Limitless tournament game, saved before the battle log is exported.

The HUD process keeps the toggle in .limitless_dashboard_state.json
("auto_end_screenshot", on by default); the monitor process (BattleEndAutomation)
takes the picture when the BATTLE LOG button shows, but only while a tournament
match is open (the .in_tournament flag the Limitless manager writes)."""

import json
import os
import re
import threading
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, ".limitless_dashboard_state.json")
TOURNAMENT_FLAG_FILE = os.path.join(BASE_DIR, ".in_tournament")
FLAG_MAX_AGE_S = 4 * 3600
FOLDER = os.path.join(os.path.expanduser("~"), "Pictures", "TCG Live Monitor", "End screens")


def enabled():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            return bool(json.load(handle).get("auto_end_screenshot", True))
    except Exception:
        return True


def tournament_opponent():
    """The current tournament opponent's name, or None outside a match."""
    try:
        if time.time() - os.path.getmtime(TOURNAMENT_FLAG_FILE) > FLAG_MAX_AGE_S:
            return None
        with open(TOURNAMENT_FLAG_FILE, "r", encoding="utf-8") as handle:
            flag = json.load(handle)
        if not flag.get("in_tournament"):
            return None
        return (flag.get("opponent") or "").strip() or "opponent"
    except Exception:
        return None


def file_name(opponent, when=None):
    when = when or datetime.now()
    safe = re.sub(r'[\\/:*?"<>|]+', "", opponent or "opponent").strip()[:40] or "opponent"
    return f"{when:%Y-%m-%d %H-%M-%S} vs {safe}.png"


def save(frame, opponent, log=print, folder=None):
    """frame: an mss grab (BGRA) or a numpy array of one. Saved on a thread
    so the export isn't held up."""
    import numpy as np
    pixels = np.asarray(frame)
    folder = folder or FOLDER
    path = os.path.join(folder, file_name(opponent))

    def work():
        try:
            from PIL import Image
            os.makedirs(folder, exist_ok=True)
            Image.fromarray(pixels[:, :, 2::-1].copy()).save(path)   # BGRA -> RGB
            log(f"End screen saved: {path}")
        except Exception as exc:
            log(f"End screen screenshot failed: {exc}")

    thread = threading.Thread(target=work, daemon=True, name="EndScreenSave")
    thread.start()
    return path, thread
