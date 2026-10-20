"""
Pokemon TCG Live ranked ladder leagues.

Single source of truth for the rank (ladder points) thresholds. Used by the
overlay's league Pokéball and by the rank-weighted win rate in
deck_analytics, so both always agree.
"""

# (min_rank, league_key, display_name), ascending.
LEAGUES = [
    (0, "nest", "Nest Ball"),
    (30, "quick", "Quick Ball"),
    (110, "poke", "Poké Ball"),
    (230, "great", "Great Ball"),
    (390, "ultra", "Ultra Ball"),
    (550, "master", "Master Ball"),
]

# Relative information weight of a game played at the START of each league.
# Weights interpolate linearly between league thresholds and are capped at
# 1.0 from Master Ball upward. Lower leagues still count, just less.
LEAGUE_WEIGHTS = {
    "nest": 0.25,
    "quick": 0.35,
    "poke": 0.50,
    "great": 0.70,
    "ultra": 0.85,
    "master": 1.00,
}


def league_for_rank(rank):
    """Return the league key for a rank value (defaults to 'poke' if unknown)."""
    try:
        value = int(rank)
    except (TypeError, ValueError):
        return "poke"
    key = LEAGUES[0][1]
    for threshold, league_key, _name in LEAGUES:
        if value >= threshold:
            key = league_key
    return key


def league_name(rank):
    key = league_for_rank(rank)
    for _threshold, league_key, name in LEAGUES:
        if league_key == key:
            return name
    return ""


# Arceus League (Master League) shows an Elo since 2026-10-11: you enter at
# 1500 and can drop below. Ranks from ELO_MIN up are that Elo (the old ladder
# points never got near it). Skill reading: under 1400 low, 1500 decent,
# 1600 high, 1700+ the very top. Weights between the anchors are linear:
#   <= 1400  "arceus_low"  (between Ultra Ball and a normal Master game)
#      1500  "master"      (a normal Master / Arceus game, 1.0)
#   >= 1650  "tournament"  (counts like a Limitless tournament game)
ELO_MIN = 1000
ELO_LOW, ELO_START, ELO_TOURNAMENT = 1400.0, 1500.0, 1650.0
ARCEUS_LOW_WEIGHT = 0.92
TOURNAMENT_WEIGHT = 3.0


def is_elo(rank):
    try:
        return float(rank) >= ELO_MIN
    except (TypeError, ValueError):
        return False


def elo_tournament_share(rank):
    """How tournament-like the opponents of a game at this Elo are, 0..1:
    0 up to 1500, 1 from 1650 (Score: high-Elo games aren't 'easier ladder')."""
    if not is_elo(rank):
        return 0.0
    return min(1.0, max(0.0, (float(rank) - ELO_START) / (ELO_TOURNAMENT - ELO_START)))


def _ladder_settings():
    try:
        from weights import load_weights
        return load_weights()["ladder"]
    except Exception:
        return {}


def _league_weights():
    """User-adjusted league weights (Advanced → Preferences), else defaults."""
    ladder = _ladder_settings()
    try:
        return {key: float(ladder.get(key, LEAGUE_WEIGHTS[key])) for key in LEAGUE_WEIGHTS}
    except (TypeError, ValueError):
        return LEAGUE_WEIGHTS


def elo_weight_for(rank):
    """Weight of an Arceus League game from its Elo (see the anchors above)."""
    ladder = _ladder_settings()
    low = float(ladder.get("arceus_low", ARCEUS_LOW_WEIGHT))
    start = float(ladder.get("master", LEAGUE_WEIGHTS["master"]))
    top = float(ladder.get("tournament", TOURNAMENT_WEIGHT))
    value = float(rank)
    if value <= ELO_LOW:
        return low
    if value < ELO_START:
        return low + (start - low) * (value - ELO_LOW) / (ELO_START - ELO_LOW)
    if value < ELO_TOURNAMENT:
        return start + (top - start) * (value - ELO_START) / (ELO_TOURNAMENT - ELO_START)
    return top


def rank_weight_for(rank):
    """Piecewise-linear weight between league anchors (default 0.25 .. 1.0);
    an Arceus League Elo uses elo_weight_for."""
    value = float(rank)
    if value >= ELO_MIN:
        return elo_weight_for(value)
    league_weights = _league_weights()
    anchors = [(threshold, league_weights[key]) for threshold, key, _ in LEAGUES]
    if value <= anchors[0][0]:
        return anchors[0][1]
    for (x0, w0), (x1, w1) in zip(anchors, anchors[1:]):
        if value < x1:
            return w0 + (w1 - w0) * (value - x0) / float(x1 - x0)
    return anchors[-1][1]
