"""
User-adjustable data weights (Dashboard → Advanced → Preferences).

Stored under "weights" in .app_settings.json; anything missing falls back to
the defaults below. Read by meta_sources (meta sheet), leagues/deck_analytics
(your own games) and the deck pages.

meta    - how much each kind of tournament data counts in the meta sheet
ladder  - how much each of YOUR games counts in your deck statistics
          (league weights interpolate between league thresholds; Limitless
          tournament games and games without a recorded rank have fixed weights)
Expansion-era multipliers (meta.era1 / meta.era2) apply to both: data from one
expansion back x0.7, two back x0.4, older is dropped.
"""

import copy
import json
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, ".app_settings.json")

DEFAULT_WEIGHTS = {
    "meta": {
        "online": 1.0,
        "in_person": 1.75,
        "worlds": 3.0,
        "japan": 0.75,
        "era1": 0.7,
        "era2": 0.4,
    },
    "ladder": {
        "nest": 0.25,
        "quick": 0.35,
        "poke": 0.50,
        "great": 0.70,
        "ultra": 0.85,
        "master": 1.00,
        "tournament": 3.0,
        "unranked": 0.5,
    },
}

# Labels + help for the Preferences panel: key -> (label, tooltip)
LABELS = {
    "meta": {
        "in_person": ("In-person events", "limitlesstcg.com Regionals, ICs, Special Events (current format only)."),
        "worlds": ("World Championship", "Replaces the in-person weight for Worlds (current format only)."),
        "japan": ("Japan (Bo1)", "Multiplier for Japanese City League results (best-of-one)."),
        "online": ("Online events", "play.limitlesstcg.com tournaments."),
        "era1": ("1 expansion back", "Data from before the newest expansion."),
        "era2": ("2 expansions back", "Older data is dropped entirely."),
    },
    "ladder": {
        "tournament": ("Limitless tournament", "Your games detected as Limitless tournament matches."),
        "master": ("Master Ball", "Your ranked games at Master Ball and above."),
        "ultra": ("Ultra Ball", None),
        "great": ("Great Ball", None),
        "poke": ("Poké Ball", None),
        "quick": ("Quick Ball", None),
        "nest": ("Nest Ball", None),
        "unranked": ("No rank recorded", "Your games where the rank wasn't read."),
    },
}

_cache = {"mtime": None, "data": None, "checked": 0.0}


def load_weights():
    """Defaults merged with the user's overrides (re-read at most every 2 s)."""
    now = time.time()
    if _cache["data"] is not None and now - _cache["checked"] < 2.0:
        return _cache["data"]
    _cache["checked"] = now
    try:
        mtime = os.path.getmtime(SETTINGS_FILE)
    except OSError:
        mtime = None
    if _cache["data"] is not None and mtime == _cache["mtime"]:
        return _cache["data"]
    merged = copy.deepcopy(DEFAULT_WEIGHTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            user = (json.load(handle) or {}).get("weights") or {}
        for group, values in user.items():
            if group in merged and isinstance(values, dict):
                for key, value in values.items():
                    if key in merged[group]:
                        merged[group][key] = max(0.0, float(value))
    except Exception:
        pass
    _cache.update(mtime=mtime, data=merged)
    return merged


def save_weights(weights):
    """Persist only the values that differ from the defaults."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            settings = json.load(handle) or {}
    except Exception:
        settings = {}
    diff = {}
    for group, values in weights.items():
        for key, value in values.items():
            if abs(float(value) - DEFAULT_WEIGHTS[group][key]) > 1e-9:
                diff.setdefault(group, {})[key] = round(float(value), 3)
    if diff:
        settings["weights"] = diff
    else:
        settings.pop("weights", None)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)
    os.replace(tmp, SETTINGS_FILE)
    _cache.update(data=None, mtime=None, checked=0.0)


def era_weights():
    """[current, 1 back, 2 back]; anything older is dropped."""
    meta = load_weights()["meta"]
    return [1.0, meta["era1"], meta["era2"]]


def cached_expansions(region="en"):
    """Expansion list from the meta sheet's cache (no network). Newest first."""
    path = os.path.join(BASE_DIR, ".meta_store", f"expansions_{region}.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            sets = json.load(handle) or []
    except Exception:
        return []
    today = time.strftime("%Y-%m-%d")
    sets = [s for s in sets if s.get("cards", 0) >= 90 and s.get("date", "9999") <= today]
    return sorted(sets, key=lambda s: s["date"], reverse=True)
