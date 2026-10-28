"""
Plain formulas (with the actual numbers plugged in) for every custom rating
and weighting, shown in hover tooltips so it's always clear what a number
means and how it was made. HTML for Qt rich-text tooltips.
"""

F = "<span style='font-family:Consolas,monospace; color:#CFE3FF'>"
END = "</span>"
DIM = "<span style='color:#8A97AA'>"


def head(title):
    """Small caps section heading inside a tip's details."""
    return f"<span style='color:#8A97AA; font-size:9px; font-weight:700; letter-spacing:1px'>{title.upper()}</span>"


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
    par = post.get("par", 0.5)
    lines = [
        f"{F}Estimate = (W + n₀ × even) / (W + L + n₀) = {a:.1f} / {a + b:.1f} = {_pct(a / (a + b))}{END}",
        f"{F}Range = {tail}th–{100 - tail}th percentile of Beta({a:.1f}, {b:.1f}){END}",
        f"{DIM}W, L = {'weighted ' if weighted else ''}wins and losses; n₀ = {n0:.0f}, like starting "
        f"{n0 / 2:.0f}-{n0 / 2:.0f}, so early streaks don't overstate the deck.{END}",
    ]
    if abs(par - 0.5) >= 0.0005:
        lines.append(f"{DIM}Even = {_pct(par)} because ties count as losses.{END}")
    return "<br>".join(lines)


def game_weights():
    """How YOUR games are weighted (Settings → Data Weights)."""
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
    mu, k_m = info.get("mu", 0.5), info.get("k_m", 0)
    lines = [
        f"{F}Score = Σ share × matchup estimate{END}  {DIM}(mirror = even, {_pct(info.get('par', 0.5))}){END}",
        f"{F}matchup estimate = (k·θ + wins) / (k + games),  k = {k_m:.0f}{END}",
        f"{F}θ (deck strength) = {_pct(res.get('strength', 0))} ± {res.get('strength_sd', 0) * 100:.1f}{END}  "
        f"{DIM}starts at "
        + (f"{archetype}'s strength" if is_mine and archetype else
           "even" if is_mine else
           f"the typical deck ({_pct(mu)})") + END,
    ]
    if res.get("in_person") and info.get("beta_link"):
        lines.append(f"{DIM}In-person Top 32 results also inform θ.{END}")
    adj = res.get("adjust")
    if is_mine and adj:
        lines.append(opponent_strength(adj, info.get("strength") or {}))
    terms = res.get("terms") or []
    if terms:
        parts = [f"{names.get(k, k)} {s * 100:.0f}% × {p * 100:.0f}%" for k, s, p, _n in terms[:2]]
        lines.append(f"{DIM}Largest: " + " + ".join(parts) + " + …" + END)
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
            f"{DIM}Nothing borrowed from Limitless: past ≈ {worth:.0f} games this is your results with the deck, "
            f"piloting included.{END}")


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
    return (f"{F}ladder games ({adj['ladder_frac'] * 100:.0f}%): − {gap:.1f} pts, × {adj['evidence']:.2f} weight{END}<br>"
            f"{DIM}Ladder opponents are weaker than a Limitless field (fades out toward 1800 Elo).{END}")
