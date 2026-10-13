---
tags: [module]
file: deck_score.py
---
# deck_score.py: Deck Score ("which decks are really the best")

**Score** = expected win rate against today's English-legal field (opponents weighted by `share_en`, mirror = 50%) from a hierarchical Bayesian model:

- θ_d ~ Beta(μ·k_s, (1−μ)·k_s) is deck strength. p_dj | θ_d ~ Beta(k_m·θ_d, k_m·(1−θ_d)) is a matchup. Results are binomial.
- **Empirical Bayes:** μ, k_s and k_m maximise the beta-binomial marginal likelihood over all archetypes / matchup cells (2026-10-12 data: μ ≈ 0.445, k_s ≈ 139 → deck strength sd ≈ 4 pts, k_m ≈ 48).
- θ posterior on a 399-point grid from all matchup cells (matchups integrated out) plus residual games. Score | θ is linear in θ, so mean/variance are exact (law of total variance). Range = moment-matched Beta, 90%.
- **Effective samples:** the meta sheet's weighted W/L is rescaled to `eff_games` = Kish n / pilot design effect (`meta_sources.py`). The pilot win-rate spread τ is measured on Limitless standings (method of moments; 0.13 online). Effective n ≈ 45% of the weighted count.
- **Your decks:** a *version* of the matched archetype. Prior mean = that archetype's θ, prior variance = its posterior variance + the fitted deck-to-deck variance (sd ≈ 4.2 pts). Pilot skill (τ ≈ 13 pts) is **not** added: it let 14 games (11-3) rank #1 at 61.4. Now 48.6 (40–57), would rank #10. Unmatched decks start at μ with the deck variance. Ranked from `MY_MIN_GAMES` = 10 games.
- Meta decks are ranked among themselves. Your decks get "would rank #N" (they never shift meta ranks). P(#1) / P(top 5) come from 4,000 joint Beta draws.
- Ties: `tie_split` (tie rule). Lanczos `lgamma` in numpy (no scipy), error ~1e-11.

UI: Meta tab "Score" + "Range" columns (sorted by Score, the old "Vs field" was removed), and the deck page **META SCORE** card + TOP 5 CHANCE tile. `StatsWindow._deck_scores(sheet, use_weights)` caches per sheet/view.

Caveat shown in the UI: your score includes your piloting and ladder opponents; meta rows are an average Limitless pilot.


Transparency: `formulas.py` builds the hover formulas with real numbers (estimate / range / chance, game weights, event weights, effective games, Score terms, pooled matchups, verdict thresholds, Share / Top cut / Converts). `score_deck` returns `terms` (opponent, share, expected rate, games) and `prior_mean` for your decks.

**Own games only** (`res['own']`): the same model with no archetype borrowing. Prior = the typical deck μ with sd = √(τ² + deck var) ≈ 13.7 pts (worth ≈ 12 games). It measures *your results with the deck* (Gengar: 62.7, would rank #1) versus the blended *deck strength* (48.6, #10). The Meta tab picks the basis for ★ rows ("scored with archetype" / "scored on own games only"), the deck page shows an OWN GAMES SCORE tile, and the Score hover shows both.

**Conversion** (`res['conversion']`): Top 32 / Day 2 as a Beta-Binomial with an empirical-Bayes prior around q0 (≈ 9.7% of Day 2 decks make Top 32). Shown as mean× with range and P(> 1.0×), so a deck with 2 Day 2 finishes can no longer claim 6×.

**No gem detector** (user decision 2026-10-12): underplayed strong decks should surface naturally from the Score (e.g. Starmie Froslass, #1 on 0.6% share).

## In-person records (2026-10-12 night)
In-person events now feed W/L and matchups from Limitless Labs pairings (whole field, every round). The Day 2 → Top 32 logit link is **not** added to θ when any row has `ip_games` (it would count the same events twice); conversion is still computed for the Converts column, and the hover drops the link line automatically (`res["in_person"]` is false).

## Par and record basis (2026-10-12 night)
- Sheet records are weighted proportions on real games (`record_basis = real_games`); `scale_of` = eff_games / raw games ≤ 1.
- `par` = an even deck's result under the tie rule, from the share-weighted field tie rate. Mirror cells are worth par; `p_above_even` = P(Score > par). Reported in `info["par"]` and `info["field_tie_rate"]`.
