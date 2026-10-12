"""Tests for the rank-weighted win rate (run: python -m pytest test_rank_weighted.py, or python test_rank_weighted.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deck_analytics import TOURNAMENT_WEIGHT, rank_weight, rank_weighted_winrate, wilson_interval
from leagues import league_for_rank


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
