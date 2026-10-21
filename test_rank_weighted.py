"""Tests for the rank-weighted win rate (run: python -m pytest test_rank_weighted.py, or python test_rank_weighted.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deck_analytics import TOURNAMENT_WEIGHT, rank_weight, rank_weighted_winrate, wilson_interval
from leagues import league_for_rank

# Pin the defaults: the user's own settings (tie mode, custom ladder weights) must not change the tests.
import copy
import deck_analytics
import weights
weights.load_weights = lambda: copy.deepcopy(weights.DEFAULT_WEIGHTS)
deck_analytics.tie_mode = lambda: "third"


def test_league_thresholds_match_overlay():
    assert [league_for_rank(r) for r in (0, 29, 30, 110, 229, 230, 389, 390, 549, 550, 900)] == [
        "nest", "nest", "quick", "poke", "poke", "great", "great", "ultra", "ultra", "master", "master"]


def test_weights_increase_with_rank_and_cap():
    weights = [rank_weight(r) for r in (0, 30, 110, 230, 390, 550, 800)]
    assert weights == sorted(weights)
    assert weights[0] == 0.25 and weights[-1] == 1.0
    # real ladder ranks no longer collapse onto one value
    assert len({round(rank_weight(r), 3) for r in (30, 100, 168, 260)}) == 4


def test_tournament_and_unranked():
    assert rank_weight(10, is_tournament=True) == TOURNAMENT_WEIGHT
    assert rank_weight(None) == 0.5


def test_equal_weights_give_plain_rate_and_full_n():
    battles = [{"result": "Win", "my_rank": 200}] * 6 + [{"result": "Loss", "my_rank": 200}] * 4
    s = rank_weighted_winrate(battles)
    assert abs(s["weighted_winrate"] - 0.6) < 1e-9
    assert abs(s["effective_n"] - 10) < 1e-9


def test_higher_rank_games_count_more():
    battles = [{"result": "Win", "my_rank": 550}] * 5 + [{"result": "Loss", "my_rank": 20}] * 5
    assert rank_weighted_winrate(battles)["weighted_winrate"] > 0.6


def test_ties_are_one_third():
    battles = [{"result": r, "my_rank": 300} for r in ("Win", "Tie", "Loss")]
    assert abs(rank_weighted_winrate(battles)["weighted_winrate"] - 4 / 9) < 1e-9


def test_wilson_known_values():
    lo, hi = wilson_interval(80, 100)
    assert abs(lo - 0.711) < 0.002 and abs(hi - 0.867) < 0.002
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0 and abs(hi - 0.278) < 0.002


def test_summary_observed_follows_the_tie_mode():
    # The old summary's observed rate used a fixed third for ties.
    old = deck_analytics.tie_mode
    try:
        for mode, expected in (("half", 6 / 10), ("third", (5 + 2 / 3) / 10), ("ignore", 5 / 8)):
            deck_analytics.tie_mode = lambda m=mode: m
            got = deck_analytics.win_rate_posterior(5, 3, 2)["observed"]
            assert abs(got - expected) < 1e-9, (mode, got)
    finally:
        deck_analytics.tie_mode = old


def test_personal_prior_is_about_19_games():
    # The prior used to be worth 4 games: a 4-0 start read "Favored".
    assert 17 <= deck_analytics.PERSONAL_PRIOR_GAMES <= 21
    post = deck_analytics.win_rate_posterior(4, 0)
    assert post["p_above_even"] < 0.9 and post["mean"] < 0.62


def test_arceus_league_elo_weights():
    # Master Ball / Arceus weight up to 1400 Elo, then a doubling curve to the
    # Limitless tournament weight at 1800: 1500 14%, 1600 33%, 1700 61%.
    from leagues import elo_tournament_share
    master = weights.DEFAULT_WEIGHTS["ladder"]["master"]
    assert rank_weight(1200) == rank_weight(1400) == master
    share = lambda r: (rank_weight(r) - master) / (TOURNAMENT_WEIGHT - master)
    for elo, expected in ((1500, 0.138), (1600, 0.333), (1700, 0.609), (1800, 1.0)):
        assert abs(share(elo) - expected) < 0.002, (elo, share(elo))
    assert rank_weight(1800) == rank_weight(2100) == TOURNAMENT_WEIGHT
    ladder = [rank_weight(r) for r in (1300, 1400, 1450, 1500, 1600, 1700, 1750, 1800)]
    assert ladder == sorted(ladder)
    steps = [rank_weight(r + 100) - rank_weight(r) for r in (1400, 1500, 1600, 1700)]
    assert steps == sorted(steps)                       # each 100 Elo adds more than the last
    assert elo_tournament_share(1400) == 0 and elo_tournament_share(1800) == 1 and elo_tournament_share(300) == 0
    assert "arceus_low" not in weights.DEFAULT_WEIGHTS["ladder"]
    assert "tournament_evidence" not in weights.DEFAULT_WEIGHTS["strength"]


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
