"""
Deck Score: one number for "which decks are REALLY the best".

Score = expected win rate against TODAY's English-legal field (each opponent
weighted by its meta share, mirror = par), estimated with a hierarchical
Bayesian model whose priors are fitted to the data itself:

    deck strength   theta_d ~ Beta(mu * k_s, (1 - mu) * k_s)
    matchup         p_dj | theta_d ~ Beta(k_m * theta_d, k_m * (1 - theta_d))
    results         wins_dj ~ Binomial(n_dj, p_dj)

* mu, k_s (how far deck strengths spread around the average) and k_m (how far
  matchups spread around a deck's strength) are fitted by maximising the
  beta-binomial marginal likelihood over every archetype / matchup cell
  (empirical Bayes) - not hand-picked.
* theta_d's posterior is computed exactly on a grid from ALL its matchup
  cells (integrating out each matchup), so a deck isn't double counted.
* Counts are EFFECTIVE samples: event weights (era x size) are rescaled with
  Kish's formula and divided by the pilot-clustering design effect
  (meta_sources.py), so 7,000 weighted games from 600 pilots count as what
  they are worth. Your own games use your weighted, Kish-rescaled records.
* Your decks are treated as a version of the archetype they match: the prior
  is centred on that archetype's measured strength with the fitted deck-to-
  deck spread (~4 pts), so it takes many games to move far from it - a 10-1
  start can't outrank decks measured over thousands of games.
* Ties are split per the tie rule (deck_analytics.tie_split).
* Par = an even deck's result under the tie rule, (1 - T)/2 + T x tie share
  (T = the field's tie rate): 50% unless ties count as losses. Mirrors are
  worth par and 'beats the field' means above par. Weighted records in the
  sheet sum to the real games (weights shift influence, never add games).

Returns per deck: score (mean, %), 90% range, P(score > 50%), rank among
qualifying decks and P(#1) / P(top 5) from joint simulation. Your decks also
get "own" (own games only, no archetype borrowing). Archetypes get a Bayesian
in-person "conversion" (Top 32 / Day 2, shrunk toward the typical rate).
"""

import math

import numpy as np

from deck_analytics import CREDIBLE_LEVEL, beta_cdf, beta_ppf, tie_par, tie_split

THETA = np.linspace(0.0025, 0.9975, 399)
_LOG_T, _LOG_1T = np.log(THETA), np.log1p(-THETA)
RANK_MARGIN = 15.0         # pts: ranked once the weighted sample gives +/- this precision at 90%
Z90 = 1.6449


def games_needed(margin_pts=RANK_MARGIN):
    """Effective (weighted, tournament-equivalent) games for +/- margin at
    90% in the worst case p = 50%:  n = (z * 0.5 / margin)^2."""
    m = max(float(margin_pts), 1.0) / 100.0
    return (Z90 * 0.5 / m) ** 2
DEFAULT_PILOT_SD = 0.08    # if the sheet predates pilot_sd


# ── maths helpers ──────────────────────────────────────────────────────
_LANCZOS = (676.5203681218851, -1259.1392167224028, 771.32342877765313,
            -176.61502916214059, 12.507343278686905, -0.13857109526572012,
            9.9843695780195716e-6, 1.5056327351493116e-7)


def lgamma(x):
    """Vectorised log-gamma for x > 0 (Lanczos, g=7, ~1e-13 relative)."""
    x = np.asarray(x, dtype=float) - 1.0
    a = np.full_like(x, 0.99999999999980993)
    for i, c in enumerate(_LANCZOS):
        a = a + c / (x + i + 1.0)
    t = x + 7.5
    return 0.5 * math.log(2 * math.pi) + (x + 0.5) * np.log(t) - t + np.log(a)


def lbeta(a, b):
    return lgamma(a) + lgamma(b) - lgamma(a + b)


def _wl(rec, scale=1.0):
    """(wins, losses) with ties split per the tie rule, times `scale`."""
    w, l, t = (float(x or 0) for x in (list(rec) + [0, 0, 0])[:3])
    tw, tl = tie_split(t)
    return (w + tw) * scale, (l + tl) * scale


def _beta_from_moments(mean, var):
    mean = min(0.999, max(0.001, mean))
    k = max(mean * (1.0 - mean) / max(var, 1e-12) - 1.0, 0.5)
    return mean * k, (1.0 - mean) * k


# ── empirical-Bayes hyperparameters ────────────────────────────────────
def fit_strength_prior(totals, mus=None):
    """(mu, k_s) maximising the beta-binomial marginal likelihood of each
    deck's (wins, losses)."""
    if not totals:
        return 0.5, 200.0
    w = np.array([t[0] for t in totals])[:, None]
    l = np.array([t[1] for t in totals])[:, None]
    best = (-np.inf, 0.5, 200.0)
    mus = np.linspace(0.30, 0.70, 81) if mus is None else mus
    for k in np.logspace(math.log10(2.0), math.log10(20000.0), 90):
        a, b = mus * k, (1.0 - mus) * k
        ll = (lbeta(w + a, l + b) - lbeta(a, b)).sum(axis=0)
        i = int(np.argmax(ll))
        if ll[i] > best[0]:
            best = (ll[i], float(mus[i]), float(k))
    return best[1], best[2]


def fit_matchup_spread(cells):
    """k_m for matchups around each deck's strength. cells: (w, l, m)."""
    if not cells:
        return 30.0
    w = np.array([c[0] for c in cells])
    l = np.array([c[1] for c in cells])
    m = np.clip(np.array([c[2] for c in cells]), 0.02, 0.98)
    ks = np.logspace(0.0, 4.0, 120)
    ll = [float((lbeta(w + k * m, l + k * (1 - m)) - lbeta(k * m, k * (1 - m))).sum()) for k in ks]
    return float(ks[int(np.argmax(ll))])


# ── one deck ───────────────────────────────────────────────────────────
def _theta_posterior(prior_a, prior_b, cells, residual, k_m, extra_loglik=None):
    """Normalised grid posterior of deck strength theta."""
    logp = (prior_a - 1.0) * _LOG_T + (prior_b - 1.0) * _LOG_1T
    if extra_loglik is not None:
        logp = logp + extra_loglik
    logp = logp + residual[0] * _LOG_T + residual[1] * _LOG_1T
    if cells:
        w = np.array([c[0] for c in cells])[:, None]
        l = np.array([c[1] for c in cells])[:, None]
        a, b = k_m * THETA[None, :], k_m * (1.0 - THETA[None, :])
        logp = logp + (lbeta(w + a, l + b) - lbeta(a, b)).sum(axis=0)
    logp -= logp.max()
    post = np.exp(logp)
    return post / post.sum()


def _cells(matchups, overall, field, own_key):
    shares = dict(field)
    cells = [(w, l) for key, (w, l) in matchups.items() if key in shares and key != own_key and w + l > 0]
    in_cells = (sum(c[0] for c in cells), sum(c[1] for c in cells))
    residual = (max(0.0, overall[0] - in_cells[0]), max(0.0, overall[1] - in_cells[1]))
    return cells, residual


def score_deck(prior_a, prior_b, matchups, overall, field, own_key, k_m, level=CREDIBLE_LEVEL, extra_loglik=None,
               par=0.5):
    """matchups: {opp_key: (w, l)} effective; overall: (W, L) effective;
    field: [(key, share)] with shares summing to 1. extra_loglik: more
    evidence about theta on the THETA grid (in-person results). par: the
    result rate of an even contest under the tie rule (mirror matches, and
    the line "beats the field" is measured against)."""
    cells, residual = _cells(matchups, overall, field, own_key)
    post = _theta_posterior(prior_a, prior_b, cells, residual, k_m, extra_loglik)

    # Score | theta is linear in theta for every opponent:
    #   faced:   E[p_j | theta] = (k_m theta + w_j) / (k_m + n_j)
    #   unfaced: E[p_j | theta] = theta;   mirror: 0.5
    const = np.zeros_like(THETA)
    slope = 0.0
    var_given = np.zeros_like(THETA)
    covered = 0.0
    terms = []
    for key, s in field:
        if key == own_key:
            const += par * s
            terms.append((key, s, par, 0.0))
            continue
        w, l = matchups.get(key, (0.0, 0.0))
        n = w + l
        a = k_m * THETA + w
        b = k_m * (1.0 - THETA) + l
        mean_j = a / (a + b)
        if n > 0:
            covered += s
        const += s * mean_j if n > 0 else 0.0
        if n <= 0:
            slope += s
        var_given += s * s * a * b / ((a + b) ** 2 * (a + b + 1.0))
        terms.append((key, s, float((post * mean_j).sum()), n))
    cond_mean = const + slope * THETA
    mean = float((post * cond_mean).sum())
    var = float((post * (var_given + cond_mean ** 2)).sum()) - mean * mean
    a, b = _beta_from_moments(mean, var)
    tail = (1.0 - level) / 2.0
    return {
        "score": mean,
        "sd": math.sqrt(max(var, 0.0)),
        "low": beta_ppf(tail, a, b),
        "high": beta_ppf(1.0 - tail, a, b),
        "p_above_even": 1.0 - beta_cdf(par, a, b),
        "par": par,
        "strength": float((post * THETA).sum()),
        "strength_sd": math.sqrt(max(float((post * THETA ** 2).sum()) - float((post * THETA).sum()) ** 2, 0.0)),
        "coverage": covered,
        "terms": sorted(terms, key=lambda x: -x[1])[:6],  # (opponent, share, expected rate, games)
        "_ab": (a, b),
    }


# ── opponent strength ──────────────────────────────────────────────────
def _logit(p):
    return math.log(p / (1.0 - p))


def adjust_personal(rec, ladder_frac, strength):
    """Your (weighted) record -> tournament-equivalent evidence.

    Ladder opponents are weaker than a Limitless field, so for the ladder part
    of the record the win rate is shifted down by `ladder_gap` points (on the
    log-odds scale, so 90% isn't pushed below 0), and every game counts
    `ladder_evidence` tournament games. Limitless tournament games you played
    count `tournament_evidence` and aren't shifted.
    Returns (wins, losses, ties, details).
    """
    w, l, t = (float(x or 0) for x in (list(rec) + [0, 0, 0])[:3])
    if not strength or w + l + t <= 0:
        return w, l, t, None
    f = min(1.0, max(0.0, float(ladder_frac)))
    gap = float(strength.get("ladder_gap", 0.0)) / 100.0
    delta = _logit(min(0.99, 0.5 + gap)) * f            # log-odds shift for the ladder share
    n_wl = w + l
    if n_wl > 0 and delta:
        p = (w + 0.5) / (n_wl + 1.0)                    # smoothed so 2-0 has a finite log-odds
        p_adj = 1.0 / (1.0 + math.exp(-(_logit(p) - delta)))
        w_new = min(n_wl, max(0.0, w + (p_adj - p) * (n_wl + 1.0)))
        w, l = w_new, n_wl - w_new
    ev = f * float(strength.get("ladder_evidence", 1.0)) + (1.0 - f) * float(strength.get("tournament_evidence", 1.0))
    return w * ev, l * ev, t * ev, {"gap": gap, "delta": delta, "evidence": ev, "ladder_frac": f}


def _in_person_loglik(t, n, beta, q0, mu, kq):
    """log P(t Top 32 out of n Day 2 | theta) for every theta on the grid:
    logit q(theta) = logit q0 + beta (theta - mu), with beta-binomial noise."""
    q = 1.0 / (1.0 + np.exp(-(_logit(q0) + beta * (THETA - mu))))
    q = np.clip(q, 1e-4, 1 - 1e-4)
    a, b = kq * q, kq * (1.0 - q)
    return lbeta(t + a, n - t + b) - lbeta(a, b)


# ── everything ─────────────────────────────────────────────────────────
def compute_scores(meta_rows, my_decks=(), *, pilot_sd=None, min_meta_games=0,
                   level=CREDIBLE_LEVEL, draws=4000, strength=None):
    """Scores for every meta archetype in the English field and your decks.

    meta_rows: meta sheet rows (wins/losses/ties weighted, eff_games, share_en,
               matchups {id: [w, l, t]} weighted).
    my_decks:  {"id", "deck", "wins", "losses", "ties" (weighted, Kish),
               "matchups" {meta id: [w, l, t]}, "raw_games", "mirror_id"}.
    Returns ({id: result}, info).
    """
    # English-legal field; a Japan-only view has no English shares, so use its own.
    share_key = "share_en" if any((r.get("share_en") or 0) > 0 for r in meta_rows) else "share"
    rows = [r for r in meta_rows if (r.get(share_key) or 0) > 0]
    n_needed = games_needed((strength or {}).get("rank_margin", RANK_MARGIN))
    total_share = sum(r[share_key] for r in rows) or 1.0
    field = [(r["id"], r[share_key] / total_share) for r in rows]
    # Par = an even deck's expected result under the tie rule, from the
    # field's tie rate (share-weighted). 50% unless ties count as losses.
    def tie_rate(r):
        g = sum(float(r.get(k) or 0) for k in ("wins", "losses", "ties"))
        return float(r.get("ties") or 0) / g if g > 0 else None
    rated = [(s, tie_rate(by)) for (key, s), by in zip(field, rows) if tie_rate(by) is not None]
    field_tie_rate = (sum(s * t for s, t in rated) / sum(s for s, _t in rated)) if rated else None
    par = tie_par(field_tie_rate)

    def scale_of(r):
        weighted = sum(float(r.get(k) or 0) for k in ("wins", "losses", "ties"))
        if weighted <= 0:
            return 0.0
        eff = r.get("eff_games")
        if eff is None:  # older sheet: never count more than the real games
            eff = min(weighted, float(r.get("raw_games") or weighted))
        return float(eff) / weighted

    prepared = {}
    for r in rows:
        s = scale_of(r)
        overall = _wl((r.get("wins"), r.get("losses"), r.get("ties")), s)
        matchups = {k: _wl(v, s) for k, v in (r.get("matchups") or {}).items()}
        # Strength evidence = the pairing results (every opponent but the
        # mirror). The standings record also holds ~30k results with no
        # pairing (no-shows, drops, double losses; ~91% losses) and mirror
        # games (50% by construction): counted as games they pulled every
        # deck's strength ~8 pts down. Standings only when there are no pairings.
        paired = [v for k, v in matchups.items() if k != r["id"]]
        pair_w, pair_l = sum(v[0] for v in paired), sum(v[1] for v in paired)
        if pair_w + pair_l > 0:
            overall = (pair_w, pair_l)
        prepared[r["id"]] = (r, overall, matchups)

    # Hyperparameters from the archetypes with real data.
    totals = [p[1] for p in prepared.values() if p[1][0] + p[1][1] >= 5]
    mu, k_s = fit_strength_prior(totals)
    cells = []
    for _r, (W, L), matchups in prepared.values():
        if W + L < 5:
            continue
        m = (W + mu * k_s) / (W + L + k_s)
        cells += [(w, l, m) for w, l in matchups.values() if w + l > 0]
    k_m = fit_matchup_spread(cells)
    prior_a, prior_b = mu * k_s, (1.0 - mu) * k_s

    # In-person evidence (Day 2 -> Top 32), Bayesian conversion first.
    # Counts: raw Day 2 finishes (honest n) at the event-WEIGHTED Top 32 rate,
    # so Worlds (x3) and current-format in-person events (x1.75) shape the rate
    # without inventing extra finishes.
    conv_rows = []
    for r in rows:
        ip = r.get("in_person") or {}
        n = float(ip.get("day2") or 0)
        if n <= 0:
            continue
        conv_rows.append((r["id"], float(ip.get("top32") or 0), n, ip.get("conversion_top32")))
    q0 = (sum(c[1] for c in conv_rows) / sum(c[2] for c in conv_rows)) if conv_rows else None
    conv_prior, beta_link, extra = None, 0.0, {}
    if q0 and 0 < q0 < 1:
        cq, kq = fit_strength_prior([(t, n - t) for _k, t, n, _c in conv_rows],
                                    mus=np.linspace(max(0.01, q0 * 0.6), min(0.99, q0 * 1.4), 41))
        conv_prior = (cq * kq, (1.0 - cq) * kq)
        weighted_t = {k: (min(n, n * c * q0) if c is not None else t) for k, t, n, c in conv_rows}
        # How strongly conversion tracks strength (beta), fitted by maximising
        # the marginal likelihood of every archetype's in-person results
        # given its online posterior. beta = 0 would mean "no link".
        posts = {}
        for key, t, n, _c in conv_rows:
            if key in prepared:
                _r, overall, matchups = prepared[key]
                c, res_ = _cells(matchups, overall, field, key)
                posts[key] = _theta_posterior(prior_a, prior_b, c, res_, k_m)
        def marginal(beta):
            ll = 0.0
            for key, t, n, _c in conv_rows:
                if key in posts:
                    lik = np.exp(_in_person_loglik(weighted_t[key], n, beta, q0, mu, kq))
                    ll += math.log(max(float((posts[key] * lik).sum()), 1e-300))
            return ll
        coarse = max(np.linspace(0.0, 40.0, 21), key=marginal)          # step 2
        beta_link = float(max(np.linspace(max(0.0, coarse - 2.0), coarse + 2.0, 17), key=marginal))  # step 0.25
        # With in-person match results (Limitless Labs) in the records, the
        # same events already shape theta; Day 2 -> Top 32 would count them twice.
        if beta_link > 0 and not any(r.get("ip_games") for r in rows):
            extra = {k: _in_person_loglik(weighted_t[k], n, beta_link, q0, mu, kq) for k, _t, n, _c in conv_rows}

    results = {}
    for key, (r, overall, matchups) in prepared.items():
        res = score_deck(prior_a, prior_b, matchups, overall, field, key, k_m, level, extra.get(key), par=par)
        res.update(eff_games=overall[0] + overall[1], is_mine=False, in_person=key in extra,
                   qualifies=float(r.get("raw_games") or 0) >= max(1, min_meta_games)
                   and overall[0] + overall[1] >= n_needed)
        results[key] = res

    # Your decks: a VERSION of the archetype they match. Prior = that
    # archetype's Score (see below); prior spread = its remaining uncertainty
    # + how much decks differ from each other (the fitted deck spread).
    # Pilot skill (tau, ~9-13 pts online) is deliberately NOT added: the Score
    # compares decks, and 10-20 ladder games must not outweigh thousands of
    # tournament games. Unmatched decks start at par.
    tau = float(pilot_sd if pilot_sd else DEFAULT_PILOT_SD)
    deck_var = mu * (1.0 - mu) / (k_s + 1.0)
    # Where your decks start. theta is a strength against the average
    # ARCHETYPE (many weak rogue rows), not against the field you meet, so
    # neither theta nor mu is the right start: mu made unmatched decks start
    # ~5 pts low, a matched theta can sit ~4 pts above the archetype's Score.
    # A version of an archetype starts where that archetype's Score is (with
    # 0 games it scores exactly the same); anything else starts at par.
    shares = dict(field)
    for d in my_decks:
        mirror = d.get("mirror_id")
        if mirror in results:
            # Score(0 games) = theta x (1 - mirror share) + par x mirror share
            s_m = min(0.9, shares.get(mirror, 0.0))
            m0 = (results[mirror]["score"] - par * s_m) / (1.0 - s_m)
            var0 = (results[mirror]["sd"] / (1.0 - s_m)) ** 2 + deck_var
        else:
            m0, var0 = par, deck_var
        pa, pb = _beta_from_moments(m0, var0)
        # Opponent strength: ladder games -> tournament-equivalent evidence.
        aw, al, at, adj = adjust_personal((d.get("wins"), d.get("losses"), d.get("ties")),
                                          d.get("ladder_frac", 1.0), strength)
        overall = _wl((aw, al, at))
        cell_frac = d.get("matchup_ladder_frac") or {}
        matchups = {k: _wl(adjust_personal(v, cell_frac.get(k, d.get("ladder_frac", 1.0)), strength)[:3])
                    for k, v in (d.get("matchups") or {}).items()}
        res = score_deck(pa, pb, matchups, overall, field, mirror, k_m, level, par=par)
        res.update(eff_games=overall[0] + overall[1], is_mine=True, mirror_id=mirror, prior_mean=m0, adjust=adj,
                   qualifies=overall[0] + overall[1] >= n_needed,
                   needs=max(0.0, n_needed - (overall[0] + overall[1])))
        # Own games only: the deck as a brand-new archetype - nothing borrowed
        # from Limitless. Prior = the typical deck with the spread of real
        # results (deck spread + pilot spread), so it measures YOUR results
        # with this deck, still adjusted for sample size.
        own_a, own_b = _beta_from_moments(par, tau * tau + deck_var)
        own = score_deck(own_a, own_b, matchups, overall, field, mirror, k_m, level, par=par)
        own.update(prior_mean=par, prior_sd=math.sqrt(tau * tau + deck_var))
        res["own"] = own
        results[d["id"]] = res

    # In-person conversion, Bayesian: Top 32 finishes out of Day 2 entries,
    # pulled toward the typical rate q0 with an empirical-Bayes prior, so a
    # deck with 2 Day 2 finishes can't claim a 6x conversion.
    if conv_prior:
        for key, top, n, _c in conv_rows:
            if key not in results:
                continue
            a, b = conv_prior[0] + top, conv_prior[1] + n - top
            results[key]["conversion"] = {
                "mean": (a / (a + b)) / q0, "p_above_1": 1.0 - beta_cdf(q0, a, b),
                "top32": top, "day2": n, "q0": q0, "alpha": a, "beta": b,
                "low": beta_ppf(0.05, a, b) / q0, "high": beta_ppf(0.95, a, b) / q0,
            }

    # Meta archetypes with enough effective games form the ranking. EVERY deck
    # (ranked, below the precision threshold, yours, own-games) gets a rank
    # position from joint simulation: in each of `draws` draws, its position =
    # 1 + number of ranked decks scoring higher. rank = position at its Score
    # (point estimate), rank_low/high = 5th/95th percentile of the simulated
    # position, plus P(#1) and P(top 5). "ranked" = enough data for a firm rank.
    ranked = sorted((k for k, v in results.items() if v["qualifies"] and not v["is_mine"]),
                    key=lambda k: -results[k]["score"])
    tail = (1.0 - level) / 2.0
    if ranked:
        rng = np.random.default_rng(7)
        a = np.array([results[k]["_ab"][0] for k in ranked])
        b = np.array([results[k]["_ab"][1] for k in ranked])
        sims = rng.beta(a[:, None], b[:, None], size=(len(ranked), draws))
        ranked_scores = np.array([results[k]["score"] for k in ranked])

        def place(v, positions):
            v["rank_low"] = int(np.quantile(positions, tail))
            v["rank_high"] = int(np.quantile(positions, 1.0 - tail))
            v["p_first"] = float((positions == 1).mean())
            v["p_top5"] = float((positions <= 5).mean())

        beaten = (sims[None, :, :] > sims[:, None, :]).sum(axis=1)  # ranked decks beating each one, per draw
        index = {k: i for i, k in enumerate(ranked)}
        for k, v in results.items():
            targets = [v] + ([v["own"]] if v.get("own") else [])
            for target in targets:
                if k in index and target is v:
                    target["rank"] = index[k] + 1
                    positions = beaten[index[k]] + 1
                else:
                    target["rank"] = 1 + int((ranked_scores > target["score"]).sum())
                    own_sims = rng.beta(target["_ab"][0], target["_ab"][1], size=draws)
                    positions = (sims > own_sims[None, :]).sum(axis=0) + 1
                target["ranked"] = bool(v["qualifies"])
                place(target, positions)

    for v in results.values():
        v.pop("_ab", None)
        if v.get("own"):
            v["own"].pop("_ab", None)
    info = {"mu": mu, "k_s": k_s, "k_m": k_m, "pilot_sd": tau, "ranked": len(ranked), "level": level,
            "strength_sd": math.sqrt(deck_var), "q0": q0, "conv_prior": conv_prior, "beta_link": beta_link,
            "in_person_decks": len(extra), "strength": strength, "n_needed": n_needed,
            "par": par, "field_tie_rate": field_tie_rate,
            "rank_margin": (strength or {}).get("rank_margin", RANK_MARGIN)}
    return results, info
