"""Tests for local_model (run: python test_local_model.py). Synthetic meta rows
and history only; no files, no DB."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import local_model as L

NOW = time.time()


def card(name, incl, avg=2.0, cat="P"):
    return {"name": name, "incl": incl, "avg": avg, "cat": cat}


META = [
    {"deck": "Dragapult", "share": 9.0, "lists": 50,
     "cards": [card("Dragapult ex", 100), card("Drakloak", 100), card("Dreepy", 100, 4)]},
    {"deck": "Gardevoir", "share": 5.0, "lists": 40,
     "cards": [card("Gardevoir ex", 100), card("Kirlia", 100), card("Ralts", 100, 4)]},
    {"deck": "Gengar", "share": 3.0, "lists": 30,
     "cards": [card("Gengar ex", 100), card("Haunter", 100), card("Gastly", 100, 4)]},
]


def game(deck, copies, opponent="", days_ago=1, weight=1.0):
    return {"deck": deck, "copies": copies, "opponent": opponent, "ts": NOW - days_ago * 86400, "weight": weight}


def test_cards_decide_when_clear():
    model = L.LocalModel(META, [], now=NOW)
    ranked = model.predict({"Gardevoir ex": 1, "Ralts": 2})
    assert ranked[0][0] == "Gardevoir" and ranked[0][1] > 0.9


def test_no_cards_falls_back_to_the_prior():
    ranked = L.LocalModel(META, [], now=NOW).predict({})
    assert [d for d, _ in ranked] == ["Dragapult", "Gardevoir", "Gengar"]


def test_ladder_frequency_moves_the_prior():
    history = [game("Gengar", {}) for _ in range(60)]
    before = dict(L.LocalModel(META, [], now=NOW).predict({}))["Gengar"]
    after = dict(L.LocalModel(META, history, now=NOW).predict({}))["Gengar"]
    assert after > 1.8 * before  # mild on purpose (LADDER_MIX_MAX): cards still decide


def test_old_games_count_less():
    recent = [game("Gardevoir", {}, days_ago=1) for _ in range(30)]
    old = [game("Gengar", {}, days_ago=120) for _ in range(30)]
    model = L.LocalModel(META, recent + old, now=NOW)
    assert model.faced[L._key("Gardevoir")] > 10 * model.faced[L._key("Gengar")]


def test_opponent_memory():
    history = [game("Gengar", {}, opponent="Rival") for _ in range(3)]
    plain = dict(L.LocalModel(META, history, now=NOW).predict({}, top=3))
    remembered = dict(L.LocalModel(META, history, now=NOW).predict({}, opponent="rival", top=3))
    assert remembered["Gengar"] > plain["Gengar"]


def test_rogue_deck_from_your_games():
    rogue = {"Spiritomb": 1, "Wailord": 1}
    history = [game("Wailord Toolbox", rogue), game("Wailord Toolbox", rogue)]
    ranked = [d for d, _ in L.LocalModel(META, history, now=NOW).predict({"Spiritomb": 1, "Wailord": 1})]
    assert "Wailord Toolbox" in ranked


def test_unknown_and_other_labels_ignored():
    model = L.LocalModel(META, [game("Unknown (local mode)", {}), game("Other", {})], now=NOW)
    assert model.faced_total == 0


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failures else 0)
