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
