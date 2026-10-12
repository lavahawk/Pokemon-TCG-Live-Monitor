"""
Helpers for deck-level statistics and Limitless archetype matching.
"""

import math
import re
from difflib import SequenceMatcher
from statistics import NormalDist

TIE_WIN_WEIGHT = 1.0 / 3.0  # default ("third"); see tie_mode()

# How ties count (TrainerHill-style "Result Rate Calculation"). Chosen in the
# Meta tab / Advanced → Preferences, stored as "tie_mode" in .app_settings.json.
TIE_MODES = {
    "ignore": ("Ignore ties", "W / (W + L)"),
    "loss": ("Ties as losses", "W / (W + L + T)"),
    "half": ("Ties as ½ win", "(W + T/2) / (W + L + T)"),
    "third": ("Ties as ⅓ win", "(W + T/3) / (W + L + T)"),
    "win": ("Ties as wins", "(W + T) / (W + L + T)"),
}
_TIE_WIN_SHARE = {"loss": 0.0, "half": 0.5, "third": 1.0 / 3.0, "win": 1.0}


_tie_cache = {"mode": None, "t": 0.0}


def tie_mode():
    """Current tie mode (settings file re-read at most every 2 s - this is
    called for every result rate, thousands of times per refresh)."""
    import time as _time
    now = _time.time()
    if _tie_cache["mode"] is None or now - _tie_cache["t"] > 2.0:
        try:
            from app_settings import load_app_settings
            mode = load_app_settings().get("tie_mode", "third")
        except Exception:
            mode = "third"
        _tie_cache.update(mode=mode if mode in TIE_MODES else "third", t=now)
    return _tie_cache["mode"]


def set_tie_mode_cached(mode):
    """Make a just-saved tie mode take effect immediately."""
    import time as _time
    _tie_cache.update(mode=mode if mode in TIE_MODES else "third", t=_time.time())


def tie_split(ties, mode=None):
    """(counted as wins, counted as losses) for `ties` under the tie mode.
    'ignore' drops ties entirely (0, 0)."""
    mode = mode or tie_mode()
    ties = float(ties or 0)
    if mode == "ignore":
        return 0.0, 0.0
    share = _TIE_WIN_SHARE[mode]
    return ties * share, ties * (1.0 - share)


def result_rate(wins, losses, ties=0.0, mode=None):
    """Result rate under the tie mode, or None with no counted games."""
    tw, tl = tie_split(ties, mode)
    total = float(wins or 0) + float(losses or 0) + tw + tl
    return (float(wins or 0) + tw) / total if total > 0 else None


IGNORED_NAME_TOKENS = {
    "deck",
    "list",
    "ptcg",
    "pokemon",
    "standard",
    "live",
    "tcg",
    "new",
}


def normalize_deck_name(name):
    text = (name or "").lower().replace("&", " and ").replace("'", "")
    text = re.sub(r"[^a-z0-9\s-]+", " ", text)
    text = text.replace("-", " ")
    tokens = [token for token in text.split() if token and token not in IGNORED_NAME_TOKENS]
    return " ".join(tokens)


def deck_tokens(name):
    return set(normalize_deck_name(name).split())


def wilson_interval(wins, total, z=1.96):
    if total <= 0:
        return 0.0, 1.0
    p = wins / total
    denom = 1.0 + (z * z) / total
    center = (p + (z * z) / (2.0 * total)) / denom
    margin = (
        z
        * math.sqrt((p * (1.0 - p) / total) + ((z * z) / (4.0 * total * total)))
        / denom
    )
    return max(0.0, center - margin), min(1.0, center + margin)


# ── Exact Beta distribution helpers (no scipy) ─────────────────────────────
#
# Win rates are modelled as Beta posteriors. The old code used a normal
# approximation for the credible range and P(WR > 50%), which is badly off
# for the small samples most decks have (it could put the range outside
# [0, 1] or claim 83% certainty from a 2-0 record), and mixed a Wilson
# interval (around the raw rate) with the Bayesian estimate. Everything now
# comes from the exact posterior, so the estimate, its range and the
# probabilities always agree.

def _betacf(a, b, x, max_iter=200, eps=3e-14):
    """Continued fraction for the incomplete beta function (Lentz)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e300
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def beta_cdf(x, a, b):
    """P(X <= x) for X ~ Beta(a, b)  (regularized incomplete beta I_x(a, b))."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_bt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
              + a * math.log(x) + b * math.log(1.0 - x))
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def beta_ppf(q, a, b):
    """Inverse CDF of Beta(a, b) by bisection (36 steps -> ~1.5e-11 precision,
    far below anything displayed)."""
    lo, hi = 0.0, 1.0
    for _ in range(36):
        mid = (lo + hi) / 2.0
        if beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


CREDIBLE_LEVEL = 0.90  # "likely range" shown in the UI: 90% of the posterior


def win_rate_posterior(wins, losses, ties=0.0, *, prior_mean=0.5, prior_strength=4.0, level=CREDIBLE_LEVEL):
    """Beta posterior for a win rate.

    prior_mean/prior_strength: the prior is worth `prior_strength` games
    centred on `prior_mean` (default Beta(2, 2): mild pull toward 50%).
    Matchups use the deck's own win rate as prior_mean (partial pooling).
    Returns mean, sd, equal-tailed `level` range, and exact P(WR > 50%).
    """
    wins = max(0.0, float(wins or 0))
    losses = max(0.0, float(losses or 0))
    ties = max(0.0, float(ties or 0))
    tie_w, tie_l = tie_split(ties)          # per the user's tie mode
    eff_wins = wins + tie_w
    eff_losses = losses + tie_l
    games = eff_wins + eff_losses           # 'ignore' leaves ties out entirely
    prior_mean = min(0.98, max(0.02, float(prior_mean)))
    a = eff_wins + prior_mean * prior_strength
    b = eff_losses + (1.0 - prior_mean) * prior_strength
    mean = a / (a + b)
    var = (a * b) / ((a + b) ** 2 * (a + b + 1.0))
    tail = (1.0 - level) / 2.0
    return {
        "games": games,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "observed": (eff_wins / games) if games else None,
        "alpha": a,
        "beta": b,
        "mean": mean,
        "sd": math.sqrt(var),
        "low": beta_ppf(tail, a, b),
        "high": beta_ppf(1.0 - tail, a, b),
        "level": level,
        "p_above_even": 1.0 - beta_cdf(0.5, a, b),
    }


def probability_above(posterior, threshold):
    """P(true win rate > threshold) under a win_rate_posterior()."""
    return 1.0 - beta_cdf(float(threshold), posterior["alpha"], posterior["beta"])


def sample_confidence(games):
    """('Low'|'Medium'|'High', plain-language note) for a sample size."""
    if games <= 0:
        return "Low", "No recorded games yet."
    if games < 10:
        return "Low", f"Only {int(games)} game{'s' if games != 1 else ''} - the range is wide; treat it as a hint."
    if games < 30:
        return "Medium", f"{int(games)} games - the estimate is taking shape but can still move."
    return "High", f"{int(games)} games - a fairly stable estimate."


def verdict_from_probability(p_above):
    """Turn P(win rate > benchmark) into a short, honest verdict."""
    if p_above >= 0.90:
        return "Favored"
    if p_above >= 0.70:
        return "Leaning favored"
    if p_above > 0.30:
        return "Too close to call"
    if p_above > 0.10:
        return "Leaning unfavored"
    return "Unfavored"


def meta_adjusted_winrate(deck_posterior, field, *, pool_strength=6.0, level=CREDIBLE_LEVEL):
    """Expected win rate against the current meta (post-stratification).

    Your raw win rate depends on who you happened to be matched against. This
    re-weights your results by each archetype's actual meta share, so a deck
    that farmed weak opponents is not flattered (and vice versa).

    field: list of {"key", "share" (percent), "wins", "losses", "ties"} for
           EVERY meta archetype (shares are normalised to sum to 1).
    Each matchup is estimated with partial pooling: a Beta prior centred on
    the deck's own win rate worth `pool_strength` games, so a 1-0 matchup
    moves the estimate only slightly. Archetypes you never faced contribute
    the deck's overall estimate (and its uncertainty).

    Returns mean, low/high (`level` range), p_above_even, coverage (share of
    the meta you've played at least once), and per-archetype rows with their
    pooled estimate and "impact": points the matchup moves the meta win rate
    above (+) or below (-) the deck's own average. Impacts sum exactly to
    (meta-adjusted mean - deck mean).
    """
    total_share = sum(max(0.0, float(f.get("share") or 0)) for f in field)
    m = deck_posterior["mean"]
    sd_m = deck_posterior["sd"]
    if total_share <= 0 or not field:
        return None
    mean = sd_sum = coverage = 0.0
    rows = []
    for f in field:
        w = max(0.0, float(f.get("share") or 0)) / total_share
        games = float(f.get("wins") or 0) + float(f.get("losses") or 0) + float(f.get("ties") or 0)
        if games > 0:
            post = win_rate_posterior(f.get("wins"), f.get("losses"), f.get("ties"),
                                      prior_mean=m, prior_strength=pool_strength, level=level)
            p, sd = post["mean"], post["sd"]
            coverage += w
        else:
            post, p, sd = None, m, sd_m
        mean += w * p
        sd_sum += w * sd
        rows.append({**f, "weight": w, "posterior": post, "estimate": p,
                     "impact": w * (p - m) * 100.0})
    # Every matchup estimate is anchored on the same (uncertain) deck win
    # rate, so their errors move together. Treat them as fully correlated:
    # sd = sum of weighted sds. This is the honest upper bound - assuming
    # independence made the meta range narrower than the deck's own range.
    sd = max(sd_sum, 1e-6)
    # Moment-matched Beta (same mean and sd): stays inside 0-100% and is
    # properly skewed near the edges, unlike a normal curve.
    mean_c = min(0.999, max(0.001, mean))
    k = max(mean_c * (1.0 - mean_c) / (sd * sd) - 1.0, 0.5)
    a, b = mean_c * k, (1.0 - mean_c) * k
    tail = (1.0 - level) / 2.0
    return {
        "mean": mean,
        "sd": sd,
        "low": beta_ppf(tail, a, b),
        "high": beta_ppf(1.0 - tail, a, b),
        "level": level,
        "p_above_even": 1.0 - beta_cdf(0.5, a, b),
        "coverage": coverage,
        "rows": rows,
    }


def bayesian_binomial_summary(wins, losses, ties=0.0, *, alpha=2.0, beta=2.0, z=1.96):
    """Backward-compatible summary used across the dashboard.

    v2.4.1: bayes/ci ranges are the exact 95% Beta credible interval and
    probability_above_even is exact (see win_rate_posterior).
    """
    wins = max(0.0, float(wins or 0))
    losses = max(0.0, float(losses or 0))
    ties = max(0.0, float(ties or 0))
    total = wins + losses + ties
    raw_observed = (wins / total) if total else 0.0
    effective_wins = wins + (TIE_WIN_WEIGHT * ties)
    observed = (effective_wins / total) if total else 0.0

    post = win_rate_posterior(wins, losses, ties, prior_mean=alpha / (alpha + beta),
                              prior_strength=alpha + beta, level=0.95)
    posterior_mean = post["mean"]
    credible_low, credible_high = post["low"], post["high"]
    # One consistent interval everywhere (it used to be a Wilson interval
    # around the raw rate shown next to the Bayesian estimate).
    ci_low, ci_high = credible_low, credible_high
    probability_above_even = post["p_above_even"]
    interval_width = ci_high - ci_low

    if total >= 30 or interval_width <= 0.18:
        confidence_label = "High"
    elif total >= 12 or interval_width <= 0.30:
        confidence_label = "Medium"
    else:
        confidence_label = "Low"

    if total == 0:
        confidence_note = "No recorded games yet."
    elif total < 5:
        confidence_note = "Very small sample. Treat the win rate as directional only."
    elif total < 12:
        confidence_note = "Early sample. The estimate is stabilized, but still swingy."
    elif total < 30:
        confidence_note = "Reasonable sample. The interval is becoming informative."
    else:
        confidence_note = "Strong sample. The estimate is relatively stable."

    return {
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "games": total,
        "raw_observed": raw_observed,
        "observed": observed,
        "bayes_mean": posterior_mean,
        "bayes_low": credible_low,
        "bayes_high": credible_high,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "probability_above_even": max(0.0, min(1.0, probability_above_even)),
        "confidence_label": confidence_label,
        "confidence_note": confidence_note,
    }


# ── Rank-weighted win rate ─────────────────────────────────────────────────
#
# PTCG Live's ranked ladder uses league thresholds (see leagues.py):
#   Nest < 30 <= Quick < 110 <= Poke < 230 <= Great < 390 <= Ultra < 550 <= Master
# A game played higher on the ladder is more informative about real deck
# strength, so each game is weighted by the league it was played in
# (0.25 at the bottom, 1.0 from Master Ball up, linear in between).
# Tournament games (Limitless) get a fixed, larger weight.
#
# v2.4: the old curve assumed a 1500-1900 Elo scale, so every real game
# (ranks 0-600) got the same 0.15 floor weight and the metric did nothing
# (BUG-007). Effective sample size now uses Kish's formula, which equals the
# game count when all weights are equal.

from leagues import rank_weight_for

TOURNAMENT_WEIGHT = 3.0
UNRANKED_WEIGHT = 0.5


def _ladder_weight(key, default):
    try:
        from weights import load_weights
        return float(load_weights()["ladder"].get(key, default))
    except Exception:
        return default


def rank_weight(rank, is_tournament=False):
    """Weight of one battle given its ladder rank (and tournament flag).
    Tournament / unranked weights are user-adjustable (Advanced → Preferences)."""
    if is_tournament:
        return _ladder_weight("tournament", TOURNAMENT_WEIGHT)
    if rank is None:
        return _ladder_weight("unranked", UNRANKED_WEIGHT)
    try:
        return rank_weight_for(float(rank))
    except (TypeError, ValueError):
        return UNRANKED_WEIGHT


def _battle_outcome_value(result):
    """Numeric outcome: 1.0 win, 0.0 loss, ties per the tie mode
    (None = tie ignored)."""
    normalized = str(result or "").strip().lower()
    if normalized == "win":
        return 1.0
    if normalized in ("tie", "draw"):
        mode = tie_mode()
        return None if mode == "ignore" else _TIE_WIN_SHARE[mode]
    return 0.0


def rank_weighted_winrate(battles, *, z=1.96):
    """Compute a rank-weighted win rate and 95% confidence interval.

    Parameters
    ----------
    battles : iterable of dicts
        Each dict has ``result`` ("Win"/"Loss"/"Tie"), ``my_rank`` (Elo or
        None), and optionally ``is_tournament`` (bool). Battles without a rank
        get a neutral weight; tournament battles get a large fixed weight.

    Returns
    -------
    dict with keys:
        games, wins, losses, ties,
        weighted_wins, weighted_total, weighted_winrate,
        effective_n, ci_low, ci_high, interval_width,
        avg_rank, min_rank, max_rank, rank_coverage,
        tournament_games, tournament_wins,
        confidence_label, confidence_note
    """
    weighted_wins = 0.0
    weighted_total = 0.0
    weight_sq_total = 0.0
    wins = losses = ties = 0
    ranks = []
    tournament_games = 0
    tournament_wins = 0

    for battle in battles or []:
        result = (battle or {}).get("result", "")
        elo = (battle or {}).get("my_rank")
        is_tournament = bool((battle or {}).get("is_tournament"))
        weight = rank_weight(elo, is_tournament=is_tournament)
        outcome = _battle_outcome_value(result)
        is_tie = str(result or "").strip().lower() in ("tie", "draw")
        if is_tie:
            ties += 1
        elif outcome == 1.0:
            wins += 1
        else:
            losses += 1
        if outcome is None:  # tie ignored under the current tie mode
            continue

        weighted_total += weight
        weight_sq_total += weight * weight
        weighted_wins += weight * outcome

        if is_tournament:
            tournament_games += 1
            if outcome == 1.0:
                tournament_wins += 1

        if elo is not None:
            ranks.append(float(elo))

    games = wins + losses + ties
    if weighted_total <= 0:
        return {
            "games": games,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "weighted_wins": 0.0,
            "weighted_total": 0.0,
            "weighted_winrate": 0.0,
            "effective_n": 0.0,
            "ci_low": 0.0,
            "ci_high": 1.0,
            "interval_width": 1.0,
            "avg_rank": None,
            "min_rank": None,
            "max_rank": None,
            "rank_coverage": 0.0,
            "tournament_games": 0,
            "tournament_wins": 0,
            "confidence_label": "Low",
            "confidence_note": "No recorded games yet.",
        }

    weighted_winrate = weighted_wins / weighted_total

    # Kish effective sample size: (sum w)^2 / sum w^2. Equals the number of
    # games when all weights are equal; shrinks when a few games dominate.
    effective_n = (weighted_total ** 2) / weight_sq_total if weight_sq_total > 0 else 0.0

    # Wilson interval on the weighted win rate using the effective sample size.
    ci_low, ci_high = wilson_interval(weighted_winrate * effective_n, effective_n, z=z)
    interval_width = ci_high - ci_low

    avg_rank = sum(ranks) / len(ranks) if ranks else None
    min_rank = min(ranks) if ranks else None
    max_rank = max(ranks) if ranks else None
    rank_coverage = (len(ranks) / games) if games else 0.0

    # Confidence tiers: weight both sample size AND rank coverage.
    if games == 0:
        confidence_label = "Low"
        confidence_note = "No recorded games yet."
    elif effective_n >= 30 and rank_coverage >= 0.5:
        confidence_label = "High"
        confidence_note = "Strong sample with good rank coverage."
    elif effective_n >= 12 and rank_coverage >= 0.3:
        confidence_label = "Medium"
        confidence_note = "Reasonable sample; interval is becoming informative."
    elif effective_n < 5:
        confidence_label = "Low"
        confidence_note = "Very small effective sample. Directional only."
    else:
        confidence_label = "Low"
        confidence_note = "Early sample or sparse rank data. Treat as directional."

    return {
        "games": games,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "weighted_wins": weighted_wins,
        "weighted_total": weighted_total,
        "weighted_winrate": weighted_winrate,
        "effective_n": effective_n,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "interval_width": interval_width,
        "avg_rank": avg_rank,
        "min_rank": min_rank,
        "max_rank": max_rank,
        "rank_coverage": rank_coverage,
        "tournament_games": tournament_games,
        "tournament_wins": tournament_wins,
        "confidence_label": confidence_label,
        "confidence_note": confidence_note,
    }


def battle_weight(battle, expansions=None):
    """Weight of one of YOUR games: expansion era x (tournament | league).

    era: games from before the newest expansion count era1 (0.7), two back
    era2 (0.4), older are dropped (0). League/tournament/unranked weights
    come from rank_weight(). All adjustable in Advanced → Preferences.
    """
    era_w = 1.0
    stamp = str(battle.get("timestamp") or "")[:10]
    if expansions and stamp:
        era = sum(1 for s in expansions if s["date"] > stamp)
        try:
            from weights import era_weights
            eras = era_weights()
        except Exception:
            eras = [1.0, 0.7, 0.4]
        era_w = eras[era] if era < len(eras) else 0.0
    return era_w * rank_weight(battle.get("my_rank"), is_tournament=bool(battle.get("is_tournament")))


def weighted_record(battles, expansions=None):
    """(wins, losses, ties) after weighting, rescaled to the EFFECTIVE sample.

    Weights change how much each game counts, but must not invent evidence:
    the weighted record is rescaled so its total equals Kish's effective
    sample size (sum w)^2 / sum w^2. With equal weights this is exactly the
    raw record; a few heavy games give a smaller, honest sample.
    """
    total = sq = wins = losses = ties = 0.0
    for b in battles or []:
        w = battle_weight(b, expansions)
        if w <= 0:
            continue
        outcome = str(b.get("result", "")).strip().lower()
        total += w
        sq += w * w
        if outcome == "win":
            wins += w
        elif outcome in ("tie", "draw"):
            ties += w
        else:
            losses += w
    if total <= 0:
        return 0.0, 0.0, 0.0
    scale = (total * total / sq) / total
    return wins * scale, losses * scale, ties * scale


def match_meta_row(deck_name, meta_rows, *, min_score=0.62):
    local_norm = normalize_deck_name(deck_name)
    local_tokens = set(local_norm.split())
    if not local_norm:
        return None

    best = None
    best_score = 0.0

    for rank, row in enumerate(meta_rows or [], start=1):
        meta_name = row.get("deck", "")
        meta_norm = normalize_deck_name(meta_name)
        meta_tokens = set(meta_norm.split())
        if not meta_norm:
            continue

        exact_match = local_norm == meta_norm
        contains_match = local_norm in meta_norm or meta_norm in local_norm
        overlap = 0.0
        if local_tokens or meta_tokens:
            overlap = len(local_tokens & meta_tokens) / max(1, len(local_tokens | meta_tokens))
        ratio = SequenceMatcher(None, local_norm, meta_norm).ratio()

        if exact_match:
            score = 1.0
        elif contains_match and (local_tokens & meta_tokens):
            score = 0.9
        else:
            if not (local_tokens & meta_tokens):
                continue
            score = (ratio * 0.58) + (overlap * 0.42)

        if score > best_score:
            best_score = score
            best = {
                "row": row,
                "rank": rank,
                "score": score,
            }

    if best and best_score >= min_score:
        return best
    return None
