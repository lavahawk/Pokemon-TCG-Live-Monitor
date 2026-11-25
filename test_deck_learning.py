"""Deck corrections (deck_learning.py) and how local_model learns from them
(run: python test_deck_learning.py). Temp store and synthetic data only."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deck_learning as DL  # noqa: E402
import local_model as L  # noqa: E402

DL.STORE_FILE = os.path.join(tempfile.mkdtemp(prefix="ptcgl_test_learning_"), ".deck_corrections.json")
NOW = time.time()


def card(name, incl, avg=2.0, cat="P"):
    return {"name": name, "incl": incl, "avg": avg, "cat": cat}


# Gardevoir lists often play a Munkidori line, so a game showing Ralts,
# Kirlia and Munkidori reads as Gardevoir to the matcher.
META = [
    {"deck": "Gardevoir ex", "share": 9.0, "lists": 50,
     "cards": [card("Gardevoir ex", 100), card("Kirlia", 100), card("Ralts", 100, 4), card("Munkidori", 60),
               card("Fezandipiti ex", 50)]},
    {"deck": "Dragapult ex", "share": 7.0, "lists": 40,
     "cards": [card("Dragapult ex", 100), card("Drakloak", 100), card("Dreepy", 100, 4)]},
]
SHOWN = {"Ralts": 3, "Kirlia": 2, "Munkidori": 2, "Fezandipiti ex": 1, "Pecharunt ex": 1}


def labelled(deck, copies, rejected=None):
    return {"deck": deck, "copies": copies, "opponent": "", "ts": NOW - 86400, "weight": 1.5,
            "manual": True, "rejected": rejected}


def test_record_only_real_corrections():
    assert DL.record("h1", "Gardevoir ex", "Munkidori Pecharunt", "AI")
    assert not DL.record("h2", "Gardevoir ex", "gardevoir  ex", "AI")   # same deck
    assert not DL.record("h3", "Unknown (local mode)", "Gardevoir ex", "Local")
    assert not DL.record("h1", "Dragapult ex", "Munkidori Pecharunt", "AI")  # first wrong guess kept
    assert DL.rejected_by_hash() == {"h1": "Gardevoir ex"}


def test_a_correction_is_right_next_time():
    before = L.LocalModel(META, [], now=NOW).predict(SHOWN)
    assert before[0][0] == "Gardevoir ex"
    history = [labelled("Munkidori Pecharunt", dict(SHOWN), rejected="Gardevoir ex")]
    model = L.LocalModel(META, history, now=NOW)
    after = model.predict(SHOWN)
    assert after[0][0] == "Munkidori Pecharunt", after
    assert model.learned_pick(SHOWN)[0] == "Munkidori Pecharunt"
    # a different game (a real Gardevoir) isn't pulled along
    real = {"Gardevoir ex": 2, "Kirlia": 3, "Ralts": 4}
    assert model.predict(real)[0][0] == "Gardevoir ex"
    assert model.learned_pick(real) is None


def test_partly_similar_games_lean_without_deciding():
    history = [labelled("Munkidori Pecharunt", dict(SHOWN), rejected="Gardevoir ex")]
    model = L.LocalModel(META, history, now=NOW)
    partial = {"Ralts": 2, "Munkidori": 1, "Pecharunt ex": 1, "Gardevoir ex": 1, "Kirlia": 1}
    plain = dict(L.LocalModel(META, [], now=NOW).predict(partial))
    leaned = dict(model.predict(partial))
    assert leaned.get("Munkidori Pecharunt", 0) > plain.get("Munkidori Pecharunt", 0)


def test_disagreeing_games_give_no_learned_pick():
    history = [labelled("Munkidori Pecharunt", dict(SHOWN)), labelled("Gardevoir ex", dict(SHOWN))]
    assert L.LocalModel(META, history, now=NOW).learned_pick(SHOWN) is None


def test_ai_and_local_names_match():
    names = ["Dragapult ex", "Gardevoir ex", "Dragapult Dusknoir", "Munkidori Pecharunt"]
    assert DL.canonical_deck("Dragapult", names) == "Dragapult ex"
    assert DL.canonical_deck("dragapult EX", names) == "Dragapult ex"
    assert DL.canonical_deck("Dusknoir Dragapult", names) == "Dragapult Dusknoir"
    assert DL.canonical_deck("Dragapult ex / Dusknoir", names) == "Dragapult Dusknoir"
    assert DL.canonical_deck("Pecharunt Munkidori", names) == "Munkidori Pecharunt"
    assert DL.canonical_deck("Mega Gardevoir ex", names) == "Mega Gardevoir ex"   # a different deck
    assert DL.canonical_deck("Raging Bolt ex", names) == "Raging Bolt ex"


def test_database_records_the_correction():
    from BattleDatabase import BattleDatabase
    db = BattleDatabase(db_path=os.path.join(os.path.dirname(DL.STORE_FILE), "battles.db"))
    battle_id = db.add_battle("Drill 3", "Gardevoir ex", "Loss", confidence=70, deck_source="AI",
                              log_hash="loghash-xyz")
    assert battle_id
    assert db.update_battle_record(battle_id, opponent_deck="Munkidori Pecharunt", deck_source="Manual",
                                   confidence=100)
    assert DL.rejected_by_hash().get("loghash-xyz") == "Gardevoir ex"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
