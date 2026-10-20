"""
Plain formulas (with the actual numbers plugged in) for every custom rating
and weighting, shown in hover tooltips so it's always clear what a number
means and how it was made. HTML for Qt rich-text tooltips.
"""

F = "<span style='font-family:Consolas,monospace; color:#CFE3FF'>"
END = "</span>"
DIM = "<span style='color:#8A97AA'>"


def _pct(x):
    return f"{x * 100:.1f}%"


def _weights():
    try:
        from weights import load_weights
        return load_weights()
    except Exception:
        from weights import DEFAULT_WEIGHTS
        return DEFAULT_WEIGHTS


def estimate(post, weighted=True):
    """Beta posterior mean / range / chance, with this deck's numbers."""
    a, b = post["alpha"], post["beta"]
    level = int(round(post.get("level", 0.9) * 100))
    tail = (100 - level) // 2
    n0 = max(0.0, a + b - float(post.get("games") or 0))  # the prior's worth in games
    lines = [
        f"{F}Estimate = (W + n₀ × par) / (W + L + n₀) = {a:.1f} / {a + b:.1f} = {_pct(a / (a + b))}{END}",
        f"{F}n₀ = {n0:.0f}{END}  {DIM}= m(1 − m) / sd² − 1 with sd = how much real win rates "
        f"spread (pilot skill + deck strength, measured on Limitless){END}",
        f"{F}Range = {tail}th–{100 - tail}th percentile of Beta({a:.1f}, {b:.1f}){END}",
        f"{F}Chance > par = P(Beta({a:.1f}, {b:.1f}) > {post.get('par', 0.5):.3f}) = {_pct(post['p_above_even'])}{END}",
        f"{F}par = (1 − T) / 2 + T × tie share = {_pct(post.get('par', 0.5))}{END}  "
        f"{DIM}(an even contest under your tie rule; T = tie rate, shrunk toward 12%){END}",
        f"{DIM}W, L = wins and losses{' after weighting' if weighted else ''}; ties split by your tie rule. "
        f"The prior is like starting {n0 / 2:.0f}-{n0 / 2:.0f} at par: "
        f"a 3-0 start isn't proof of a great deck; past ~{n0:.0f} games your results outweigh it.{END}",
    ]
    if weighted:
        lines.append(game_weights())
    return "<br>".join(lines)


def game_weights():
    """How YOUR games are weighted (Advanced → Preferences)."""
    lad = _weights()["ladder"]
    meta = _weights()["meta"]
    return (f"{F}game weight = era × league{END}<br>"
            f"{DIM}era: current set 1.0 · one back {meta['era1']:g} · two back {meta['era2']:g} · older 0<br>"
            f"league: Nest {lad['nest']:g} · Quick {lad['quick']:g} · Poké {lad['poke']:g} · Great {lad['great']:g} · "
            f"Ultra {lad['ultra']:g} · Master {lad['master']:g} (linear in between) · "
            f"Limitless tournament {lad['tournament']:g} · unranked {lad['unranked']:g}{END}<br>"
            f"{F}effective games = (Σ weight)² / Σ weight²{END} "
            f"{DIM}(weights change how much each game counts, never invent extra games){END}")


def event_weights():
    """How Limitless events are weighted in the meta sheet."""
    m = _weights()["meta"]
    return (f"{F}event weight = era × type × clip(√(players / 64), 0.5, 3){END}<br>"
            f"{DIM}era: current 1.0 · one back {m['era1']:g} · two back {m['era2']:g} · older dropped<br>"
            f"type: online {m['online']:g} · in-person {m['in_person']:g} · Worlds {m['worlds']:g} "
            f"(in-person boosts only in the current format) · Japan ×{m['japan']:g}{END}")


def effective_games(row, pilot_sd=None):
    raw = row.get("raw_games") or 0
    eff = row.get("eff_games")
    tau = f"{pilot_sd * 100:.0f}%" if pilot_sd else "τ"
    lines = [f"{F}evidence (effective sample size) = Kish n ÷ design effect{END}",
             f"{F}Kish n = (Σ w·g)² / Σ w²·g{END}  {DIM}(w = event weight, g = games){END}",
             f"{F}design effect = 1 + τ² / (p(1 − p)) × (avg rounds per player − 1),  τ = {tau}{END}",
             f"{DIM}τ = how much players of the same deck differ (measured from Limitless standings). "
             f"One player's rounds aren't independent games, so they count for less.{END}"]
    if eff is not None:
        lines.append(f"{F}{raw:,} games played (mirror games count once for each player){END}")
        lines.append(f"{F}evidence ≈ {eff:,.0f}{END}  {DIM}= how many independent, equally weighted games "
                     f"would give the same certainty. A statistical size used for the ranges, not data points: "
                     f"weights change how much each game counts, never how many games there are.{END}")
    return "<br>".join(lines)


def score(res, info, is_mine=False, names=None, archetype=None):
    names = names or {}
    mu, k_s, k_m = info.get("mu", 0.5), info.get("k_s", 0), info.get("k_m", 0)
    lines = [
        f"{F}Score = Σ share × matchup estimate{END}  {DIM}(each opponent by its meta share; mirror = par {_pct(info.get('par', 0.5))}){END}",
        f"{F}matchup estimate = (k·θ + wins) / (k + games),  k = {k_m:.0f}{END}",
        f"{F}θ (deck strength) = {_pct(res.get('strength', 0))} ± {res.get('strength_sd', 0) * 100:.1f}{END}  "
        f"{DIM}from all its matchups, starting at "
        + (f"{archetype}'s Score ({_pct(res.get('prior_mean', mu))} as strength)" if is_mine and archetype else
           f"par ({_pct(res.get('prior_mean', info.get('par', 0.5)))})" if is_mine else
           f"the typical archetype ({_pct(mu)}, worth {k_s:.0f} games)") + END,
    ]
    if res.get("in_person") and info.get("beta_link"):
        lines.append(f"{F}+ in-person: logit(Top 32 rate) = logit({info.get('q0', 0) * 100:.1f}%) + "
                     f"{info['beta_link']:.0f} × (θ − {_pct(mu)}){END}  {DIM}Day 2 → Top 32 results (Worlds and "
                     f"current-format events weighted up) also inform θ; the {info['beta_link']:.0f} is fitted.{END}")
    adj = res.get("adjust")
    if is_mine and adj:
        lines.append(opponent_strength(adj, info.get("strength") or {}))
    terms = res.get("terms") or []
    if terms:
        parts = [f"{names.get(k, k)} {s * 100:.1f}% × {p * 100:.0f}%" for k, s, p, _n in terms[:4]]
        lines.append(f"{DIM}biggest terms: " + " + ".join(parts) + " + …" + END)
    lines.append(f"{DIM}k, the typical deck and its spread are fitted to all Limitless data "
                 f"(empirical Bayes), not chosen by hand. Unfaced opponents count at θ. Range = 90% "
                 f"of the uncertainty in θ and every matchup.{END}")
    if is_mine:
        lines.append(f"{DIM}Your deck counts as a version of {archetype or 'an average deck'}: it starts at that "
                     f"strength ± {info.get('strength_sd', 0) * 100:.1f} (how much decks differ), so a handful of "
                     f"games moves it only a little. Your games use your Preferences weights.{END}")
    return "<br>".join(lines)


def pooled_matchup(post, deck_mean, strength=6.0):
    a, b = post["alpha"], post["beta"]
    return (f"{F}matchup estimate = (W + {strength:g}·m) / (W + L + {strength:g}) = {a:.1f} / {a + b:.1f} = "
            f"{_pct(a / (a + b))}{END}<br>{DIM}m = this deck's overall estimate ({_pct(deck_mean)}): a matchup "
            f"leans on it until you've played it a few times.{END}")


def verdict(p, par=0.5):
    return (f"{F}Chance > {'50%' if abs(par - 0.5) < 0.0005 else 'par ' + _pct(par)} = {_pct(p)}{END}<br>"
            f"{DIM}Favored ≥ 90% · Leaning favored ≥ 70% · Too close to call 30–70% · "
            f"Leaning unfavored ≤ 30% · Unfavored ≤ 10%{END}")


SHARE = (f"{F}Share = Σ event weight × (deck's entries / event entries) ÷ Σ event weight{END}")
TOP_CUT = (f"{F}Top cut = Σ event weight × (deck's placement points / event points) ÷ Σ event weight{END}<br>"
           f"{DIM}in-person: Limitless placement points · Japan City Leagues: 17 − place{END}")
CONVERTS = (f"{F}Converts = (weighted share of Top 32 spots) ÷ (weighted share of Day 2 spots){END}<br>"
            f"{DIM}1.0× = reaches Top 32 exactly as often as its popularity predicts; 1.5× = 50% more often.{END}")


def own_score(own, info):
    m, sd = own.get("prior_mean", 0.5), max(own.get("prior_sd", 0.1), 1e-6)
    worth = max(m * (1 - m) / (sd * sd) - 1, 0)
    return (f"{F}same Score formula; θ starts at par {_pct(m)} ± {sd * 100:.1f} "
            f"(worth ≈ {worth:.0f} games){END}<br>"
            f"{DIM}Own games only: nothing borrowed from the Limitless archetype. The ± is how much real results "
            f"spread (deck differences + player skill, both measured on Limitless). Your games outweigh that "
            f"starting point once you have more than ≈ {worth:.0f}, so this shows YOUR results with the deck - "
            f"including your piloting - rather than the deck's strength.{END}")


def conversion(conv):
    a, b, q0 = conv["alpha"], conv["beta"], conv["q0"]
    return (f"{F}Converts = (Top 32 + a) / (Day 2 + a + b) ÷ q0 = {a:.1f} / {a + b:.1f} ÷ {q0 * 100:.1f}% "
            f"= {conv['mean']:.2f}×{END}<br>"
            f"{F}range {conv['low']:.2f}–{conv['high']:.2f}× · chance above 1.0× = {conv['p_above_1'] * 100:.0f}%{END}<br>"
            f"{DIM}{conv['top32']} Top 32 out of {conv['day2']} Day 2 finishes. q0 = how often any Day 2 deck makes "
            f"Top 32. a, b = a prior fitted to every archetype, so a deck with a few finishes stays near 1.0×. "
            f"1.0× = converts exactly as its popularity predicts.{END}")


def opponent_strength(adj, strength):
    gap = adj["gap"] * 100
    return (f"{F}your games: win rate − {gap:.1f} pts on the ladder share ({adj['ladder_frac'] * 100:.0f}%), "
            f"then × {adj['evidence']:.2f} as evidence{END}<br>"
            f"{DIM}Ladder opponents are weaker than a Limitless field: shift = logit(50% + gap) on the log-odds "
            f"scale; one ladder game counts {strength.get('ladder_evidence', 1):g} tournament games, your Limitless "
            f"games {strength.get('tournament_evidence', 1):g}. Set in Advanced → Preferences → Opponent strength.{END}")
