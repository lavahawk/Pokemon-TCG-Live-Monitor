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


def _league_weights():
    """User-adjusted league weights (Advanced → Preferences), else defaults."""
    try:
        from weights import load_weights
        ladder = load_weights()["ladder"]
        return {key: float(ladder.get(key, LEAGUE_WEIGHTS[key])) for key in LEAGUE_WEIGHTS}
    except Exception:
        return LEAGUE_WEIGHTS


def rank_weight_for(rank):
    """Piecewise-linear weight between league anchors (default 0.25 .. 1.0)."""
    value = float(rank)
    league_weights = _league_weights()
    anchors = [(threshold, league_weights[key]) for threshold, key, _ in LEAGUES]
    if value <= anchors[0][0]:
        return anchors[0][1]
    for (x0, w0), (x1, w1) in zip(anchors, anchors[1:]):
        if value < x1:
            return w0 + (w1 - w0) * (value - x0) / float(x1 - x0)
    return anchors[-1][1]
