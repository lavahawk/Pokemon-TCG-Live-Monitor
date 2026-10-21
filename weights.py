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
    # Opponent strength (deck_score.adjust_personal): how your games compare
    # with Limitless tournament games as evidence of deck strength.
    "strength": {
        "ladder_evidence": 0.5,
        "ladder_gap": 4.0,
        "rank_margin": 15.0,
    },
}

# Labels + help for the Preferences panel: key -> (label, tooltip)
M = "<!--more-->"  # infotip.MORE (literal: this module must not import Qt)

LABELS = {
    "meta": {
        "in_person": ("In-person events", "Regionals, Internationals, Special Events (current format)."),
        "worlds": ("World Championship", "Used instead of the in-person weight for Worlds."),
        "japan": ("Japan (Bo1)", "Japanese City League results (best-of-one)."),
        "online": ("Online events", "Online tournaments on play.limitlesstcg.com."),
        "era1": ("1 expansion back", "Data from before the newest expansion."),
        "era2": ("2 expansions back", "Older data is dropped entirely."),
    },
    "ladder": {
        "tournament": ("Limitless tournament", "Games detected as Limitless tournament matches." + M
                       + "Ladder games reach this weight at 1800+ Elo."),
        "master": ("Master Ball / Arceus", "Master Ball and Arceus games, up to 1400 Elo." + M
                   + "Above 1400 the weight climbs toward the tournament weight, each 100 Elo "
                     "more than the last: 1500 +14%, 1600 +33%, 1700 +61%, 1800+ full."),
        "ultra": ("Ultra Ball", None),
        "great": ("Great Ball", None),
        "poke": ("Poké Ball", None),
        "quick": ("Quick Ball", None),
        "nest": ("Nest Ball", None),
        "unranked": ("No rank recorded", "Games where the rank wasn't read."),
    },
    "strength": {
        "ladder_evidence": ("Ladder game counts as", "One ladder game counts as this many tournament games." + M
                            + "Used in the deck Score, since ladder opponents are weaker. Fades to a full "
                              "game as your Elo nears 1800; Limitless games always count 1."),
        "ladder_gap": ("Ladder opponents easier by", "Win-% points ladder is easier than online events." + M
                       + "Measured at 50% on a log-odds scale. Fades to 0 as your Elo nears 1800."),
        "rank_margin": ("Rank precision", "Decks rank once their win rate is known within ± this many points." + M
                        + "At 90% confidence: n = (1.645 × 0.5 / margin)² effective games "
                          "(15 pts = 30 games)."),
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
