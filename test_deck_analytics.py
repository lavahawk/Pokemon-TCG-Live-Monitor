"""meta_adjusted_winrate: par, leave-one-cell-out pooling, variance (no network, no DB)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deck_analytics

deck_analytics.tie_mode = lambda: "half"

from deck_analytics import meta_adjusted_winrate


def _deck(a, b, par=0.5):
    n = a + b
    return {"mean": a / n, "sd": math.sqrt(a * b / (n * n * (n + 1.0))), "alpha": a, "beta": b, "par": par}


def test_p_above_even_is_measured_against_par():
    deck = {"mean": 0.5, "sd": 0.1, "par": 0.6}
    res = meta_adjusted_winrate(deck, [{"key": "x", "share": 100, "wins": 0, "losses": 0, "ties": 0}])
    assert res["par"] == 0.6
    assert res["p_above_even"] < 0.5, res["p_above_even"]   # against 0.5 it would be 0.5
    flat = meta_adjusted_winrate({"mean": 0.5, "sd": 0.1}, [{"key": "x", "share": 100}])
    assert flat["par"] == 0.5 and abs(flat["p_above_even"] - 0.5) < 0.02


def test_pooling_target_leaves_the_cell_out():
    # Deck Beta(10, 10); the only cell is 4-0, so the target without those games is 6/16.
    deck = _deck(10.0, 10.0)
    res = meta_adjusted_winrate(deck, [{"key": "x", "share": 100, "wins": 4, "losses": 0, "ties": 0}])
    expect = (4 + 0.375 * 6) / (4 + 6)          # 0.625, not (4 + 0.5 * 6) / 10 = 0.7
    assert abs(res["rows"][0]["estimate"] - expect) < 1e-9, res["rows"][0]["estimate"]
    assert abs(res["mean"] - expect) < 1e-9


def test_impacts_still_sum_to_mean_minus_deck_mean():
    deck = _deck(10.0, 10.0)
    field = [{"key": "x", "share": 60, "wins": 4, "losses": 0}, {"key": "y", "share": 40}]
    res = meta_adjusted_winrate(deck, field)
    assert abs(sum(r["impact"] for r in res["rows"]) / 100.0 - (res["mean"] - deck["mean"])) < 1e-9


def test_sd_is_shared_deck_term_plus_independent_cells():
    deck = _deck(10.0, 10.0)
    only_unseen = meta_adjusted_winrate(deck, [{"key": "y", "share": 100}])
    assert abs(only_unseen["sd"] - deck["sd"]) < 1e-9       # lambda = 1, no cell variance
    field = [{"key": "x", "share": 50, "wins": 3, "losses": 1}, {"key": "y", "share": 50}]
    res = meta_adjusted_winrate(deck, field)
    sd_cell = res["rows"][0]["posterior"]["sd"]
    lam_sum = 0.5 * (6.0 / (6.0 + 4.0)) + 0.5
    expect = math.sqrt(deck["sd"] ** 2 * lam_sum ** 2 + 0.25 * sd_cell ** 2)
    assert abs(res["sd"] - expect) < 1e-9, (res["sd"], expect)
    assert res["sd"] < 0.5 * sd_cell + 0.5 * deck["sd"]      # below the old fully-correlated bound


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
