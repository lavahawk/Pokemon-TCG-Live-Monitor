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


# ── Rank-weighted Elo win rate ──────────────────────────────────────────────
#
# In Pokemon TCG Live, the ladder's "Masterball" league is where real skill
# begins to show. The Elo scale is roughly:
#   < 1500  : below Masterball — results are heavily discounted
#   1500    : average (won slightly more than lost)
#   1600    : above average
#   1700    : serious players
#   1800-1900 : professional / top players
#
# A win at 1800 is far more informative than a win at 1200. So instead of
# treating every battle equally, we weight each battle by the rank it was
# played at. Below Masterball the weight is heavily penalized; above it the
# weight grows with rank.

# Elo at which we consider a player to have "arrived" at real competition.
MASTERBALL_ELO = 1500.0
# Elo at which a battle is worth full weight (1.0).
FULL_WEIGHT_ELO = 1700.0
# How steeply weight grows above Masterball (logistic steepness).
RANK_STEEPNESS = 0.008
# Weight floor for battles below Masterball (never fully zero, but heavily
# discounted so a few low-rank games can't dominate the estimate).
LOW_RANK_FLOOR = 0.15

# Tournament games are played by serious, competitive players, so they carry
# far more signal than ladder games. A tournament game is worth this many
# times a full-weight (Elo 1700+) ladder game.
TOURNAMENT_WEIGHT = 3.0


def rank_weight(elo, is_tournament=False):
    """Map an Elo (and tournament flag) to a battle weight.

    Below Masterball the weight is heavily penalized (approaching the floor).
    At Masterball it is ~0.5, and it saturates toward 1.0 as Elo rises past
    ~1700. Uses a logistic curve so the transition is smooth and monotonic.

    Tournament games bypass the rank penalty entirely and are given a large
    fixed weight (TOURNAMENT_WEIGHT), since only strong, competitive players
    enter Limitless tournaments.
    """
    if is_tournament:
        return TOURNAMENT_WEIGHT
    if elo is None:
        # No rank recorded — treat as a neutral, below-average weight so we
        # don't over-count unranked games, but don't discard them entirely.
        return 0.5
    elo = float(elo)
    # Logistic centered at Masterball, scaled so weight(1500) ≈ 0.5.
    logistic = 1.0 / (1.0 + math.exp(-RANK_STEEPNESS * (elo - MASTERBALL_ELO)))
    # Rescale so that at Masterball the weight is exactly 0.5 and it rises to
    # ~1.0 at FULL_WEIGHT_ELO, while never dropping below the floor.
    weight = LOW_RANK_FLOOR + (1.0 - LOW_RANK_FLOOR) * logistic
    return max(LOW_RANK_FLOOR, min(1.0, weight))


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

    # Effective sample size: the number of "full-weight" battles the weighted
    # data is equivalent to. We use the total weight (sum of weights), which
    # directly reflects that low-rank games carry less information than
    # high-rank games. E.g. 10 wins at Elo 1200 (weight ~0.22) is equivalent
    # to only ~2.2 full-weight games, so its confidence interval is wide.
    effective_n = weighted_total

    # Wilson interval on the weighted win rate using the effective sample size.
    ci_low, ci_high = wilson_interval(weighted_wins, effective_n, z=z)
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
