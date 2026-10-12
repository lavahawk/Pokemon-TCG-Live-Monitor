"""
Helpers for deck-level statistics and Limitless archetype matching.
"""

import math
import re
from difflib import SequenceMatcher
from statistics import NormalDist

TIE_WIN_WEIGHT = 1.0 / 3.0


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


def bayesian_binomial_summary(wins, losses, ties=0.0, *, alpha=2.0, beta=2.0, z=1.96):
    wins = max(0.0, float(wins or 0))
    losses = max(0.0, float(losses or 0))
    ties = max(0.0, float(ties or 0))
    total = wins + losses + ties
    raw_observed = (wins / total) if total else 0.0
    effective_wins = wins + (TIE_WIN_WEIGHT * ties)
    effective_losses = losses + ((1.0 - TIE_WIN_WEIGHT) * ties)
    observed = (effective_wins / total) if total else 0.0

    post_alpha = effective_wins + alpha
    post_beta = effective_losses + beta
    posterior_mean = post_alpha / (post_alpha + post_beta)

    variance = (post_alpha * post_beta) / (
        ((post_alpha + post_beta) ** 2) * (post_alpha + post_beta + 1.0)
    )
    posterior_sd = math.sqrt(max(variance, 1e-12))
    credible_low = max(0.0, posterior_mean - (z * posterior_sd))
    credible_high = min(1.0, posterior_mean + (z * posterior_sd))

    ci_low, ci_high = wilson_interval(effective_wins, total, z=z)
    probability_above_even = 1.0 - NormalDist(posterior_mean, posterior_sd).cdf(0.5)
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


def rank_weight(rank, is_tournament=False):
    """Weight of one battle given its ladder rank (and tournament flag)."""
    if is_tournament:
        return TOURNAMENT_WEIGHT
    if rank is None:
        return UNRANKED_WEIGHT
    try:
        return rank_weight_for(float(rank))
    except (TypeError, ValueError):
        return UNRANKED_WEIGHT


def _battle_outcome_value(result):
    """Return the numeric outcome of a battle: 1.0 win, 0.0 loss, 1/3 tie."""
    normalized = str(result or "").strip().lower()
    if normalized == "win":
        return 1.0
    if normalized in ("tie", "draw"):
        return TIE_WIN_WEIGHT
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

        weighted_total += weight
        weight_sq_total += weight * weight
        weighted_wins += weight * outcome

        if outcome == 1.0:
            wins += 1
        elif outcome == TIE_WIN_WEIGHT:
            ties += 1
        else:
            losses += 1

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
