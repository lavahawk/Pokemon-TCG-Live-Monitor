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


# Master Ball became the Arceus League, which shows an Elo (since
# 2026-10-11; you enter at 1500). Ranks from ELO_MIN up are that Elo (the old
# ladder points never got near it). It is a semi-Elo ladder: past ~1400 every
# 100 points is a clearly harder field, ~1700 is where games become good
# practice and ~1800 is where tournament players live (players' reports: good
# practice from 1750-1800, Day 2 players hang around 1800+, ~2000 is the top).
# So the weight of a game climbs from the Master weight at 1400 to the
# Limitless tournament weight at 1800, each 100 Elo adding more than the last:
#   share = (2^((Elo - 1400) / 200) - 1) / 3      0 at 1400, 1 at 1800
#   1500: 14%   1600: 33%   1700: 61%   1800+: 100%
ELO_MIN = 1000
ELO_BASE, ELO_TOP = 1400.0, 1800.0
TOURNAMENT_WEIGHT = 3.0


def is_elo(rank):
    try:
        return float(rank) >= ELO_MIN
    except (TypeError, ValueError):
        return False


def elo_share(rank):
    """How far an Arceus League Elo is from a Master game (0) to tournament
    strength (1), on the curve above."""
    if not is_elo(rank):
        return 0.0
    x = (min(ELO_TOP, max(ELO_BASE, float(rank))) - ELO_BASE) / ((ELO_TOP - ELO_BASE) / 2.0)
    return (2.0 ** x - 1.0) / 3.0


def elo_tournament_share(rank):
    """How tournament-like the opponents of a game at this Elo are, 0..1
    (deck Score: an 1800 game isn't 'easier ladder' any more)."""
    return elo_share(rank)


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
    """Weight of an Arceus League game from its Elo: the Master weight up to
    1400, then the curve above up to the Limitless tournament weight at 1800."""
    ladder = _ladder_settings()
    start = float(ladder.get("master", LEAGUE_WEIGHTS["master"]))
    top = float(ladder.get("tournament", TOURNAMENT_WEIGHT))
    return start + (top - start) * elo_share(rank)


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
