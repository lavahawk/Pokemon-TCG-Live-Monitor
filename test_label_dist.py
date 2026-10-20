"""label_dist: splitting a game between its label and the card read (no network, no DB)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deck_analytics

deck_analytics.tie_mode = lambda: "half"

import label_dist as L
from deck_analytics import weighted_record


def _shares(dist):
    return dict(dist)


def test_manual_and_cardless_labels_count_fully():
    assert L.distribution("Gengar", "Manual", [("Dragapult", 0.9)]) == [("Gengar", 1.0)]
    assert L.distribution("Gengar", "AI", None) == [("Gengar", 1.0)]
    assert L.distribution("Gengar", "AI", []) == [("Gengar", 1.0)]


def test_agreeing_cards_keep_most_of_the_game_on_the_label():
    d = _shares(L.distribution("Gengar", "AI", [("Gengar", 0.95), ("Zoroark", 0.04), ("Other", 0.01)]))
    assert abs(sum(d.values()) - 1.0) < 1e-9
    assert d["Gengar"] > 0.8


def test_disagreeing_cards_take_up_to_half():
    d = _shares(L.distribution("Dragapult", "AI", [("Lucario Hariyama", 0.97), ("Gengar", 0.03)]))
    assert abs(sum(d.values()) - 1.0) < 1e-9
    assert abs(d["Dragapult"] - L.LABEL_WEIGHT) < 1e-9
    assert d["Lucario Hariyama"] > 0.4


def test_tempering_flattens_overconfident_cards():
    t = dict(L.temper([("A", 0.81), ("B", 0.19)]))
    assert 0.6 < t["A"] < 0.75  # sqrt: 0.9 / (0.9 + 0.436)


def test_half_games_count_half_in_a_record():
    # Kish ignores a common factor: a cell of half-games must not become full games again.
    games = [{"result": "win", "frac": 0.5}, {"result": "loss", "frac": 0.5}]
    w, l, t = weighted_record(games)
    assert abs(w - 0.5) < 1e-9 and abs(l - 0.5) < 1e-9 and t == 0
    w, l, t = weighted_record([{"result": "win"}, {"result": "loss"}])
    assert (w, l) == (1.0, 1.0)


def test_cells_share_one_kish_scale():
    ws = [1.0] * 10 + [0.25] * 10
    assert abs(L.kish_scale(ws) * sum(ws) - 14.7059) < 1e-3
    cells = {"a": [(w, 1.0, "win" if i % 2 else "loss") for i, w in enumerate(ws[:10])],
             "b": [(w, 1.0, "tie" if i == 0 else "win") for i, w in enumerate(ws[10:])]}
    out = L.scaled_cells(cells, ws)
    assert abs(sum(sum(v) for v in out.values()) - 14.7059) < 1e-3
    half = L.scaled_cells({"a": [(1.0, 0.5, "win")]}, [1.0])
    assert abs(half["a"][0] - 0.5) < 1e-9


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
