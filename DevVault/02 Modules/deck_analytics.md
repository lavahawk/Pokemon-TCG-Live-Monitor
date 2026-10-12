---
tags: [module, analytics]
file: deck_analytics.py
lines: 355
---
# deck_analytics.py: statistics

- `wilson_interval(w, n)`: standard Wilson score CI (verified against known values in `test_rank_weighted.py`).
- `bayesian_binomial_summary(w, l, t)`: Beta(2,2) prior; ties count 1/3 win; returns observed, posterior mean, normal-approx credible band, **Wilson CI on raw data** (the UI pairs it with the Bayes mean, which can fall outside it), P(p>0.5), confidence label/note.
- `rank_weight(elo, is_tournament)`: logistic around 1500 with floor 0.15; tournament = 3.0. **Mis-calibrated for the real 0–260 rank scale** (BUG-007): every game = 0.15.
- `rank_weighted_winrate(battles)`: weighted mean, `effective_n = sum(weights)`, Wilson on the weighted counts.
- `match_meta_row(name, rows)`: normalize (drop "deck/ptcg/live/new…" tokens) → exact 1.0 / containment 0.9 / 0.58·SequenceMatcher + 0.42·Jaccard ≥ 0.62.

Statistical notes for Phase 2: the Wilson interval with a fractional n is a heuristic (fine for display); Kish's effective n `(Σw)²/Σw²` would be more standard than `Σw`; ties at 1/3 is an arbitrary convention, so document it in the UI.
