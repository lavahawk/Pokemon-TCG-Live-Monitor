"""Conceded battles: the game goes from the battle straight to the main menu,
the overlay asks, Yes adds a loss (run: python test_concede.py). Temp files
and a temp database; no screen."""
import os
import shutil
import sys
import tempfile
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import BattleDatabase as BDB
import deck_confirm as C

TMP = tempfile.mkdtemp(prefix="concede_test_")
C.LOG_DIR = TMP
C.CONCEDE_FILE = os.path.join(TMP, ".concede_check.json")


def test_question_round_trip_and_asked_once():
    C.ask_concede(1000.0, "Gengar Testing", 1510, 1498)
    q = C.read_concede()
    assert q["my_deck"] == "Gengar Testing" and q["rank_after"] == 1498
    C.mark_concede_handled()
    assert C.read_concede() is None


def test_rank_line_only_when_the_rank_moved():
    assert "1510 → 1498" in C.concede_text({"rank_before": 1510, "rank_after": 1498})
    assert "Rank" not in C.concede_text({"rank_before": 1510, "rank_after": 1510})  # not Master league
    assert "Rank" not in C.concede_text({"rank_before": None, "rank_after": 1510})


def test_yes_adds_one_loss_with_the_new_rank():
    db = BDB.BattleDatabase(os.path.join(TMP, "battles.db"))
    q = {"battle_started": 1234.0, "my_deck": "Gengar Testing", "rank_after": 1498}
    battle_id = C.record_concede(db, q)
    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute("SELECT my_deck, opponent_deck, result, my_rank, deck_source FROM battles WHERE id=?",
                           (battle_id,)).fetchone()
    assert row == ("Gengar Testing", "Unknown", "Loss", 1498, "Conceded")
    assert C.record_concede(db, q) is None  # the same battle is never added twice


class FakeMenu:
    """RankDetector stand-in: is_on_main_menu() answers from `on_menu`."""
    on_menu = False

    def is_on_main_menu(self, validation_method="auto"):
        return FakeMenu.on_menu


sys.modules["RankDetector"] = types.SimpleNamespace(RankDetector=FakeMenu)
import BattleEndAutomation as B

B.MENU_CHECK_EVERY_S = 0.02
B.MENU_WATCH_S = 2


def watcher():
    asked = []
    auto = B.BattleEndAutomation(lambda msg: None, lambda **k: None, lambda p: None,
                                 on_menu_without_end=asked.append)
    auto._battle_since, auto._last_hud_at = 100.0, 200.0
    return auto, asked


def run_watch(auto, change=None):
    t = threading.Thread(target=auto._watch_for_menu, args=(100.0, 200.0))
    t.start()
    if change:
        time.sleep(0.05)
        change()
    t.join(3)


def test_menu_after_battle_asks_once():
    FakeMenu.on_menu = True
    auto, asked = watcher()
    run_watch(auto)
    assert asked == [100.0] and auto._battle_since is None


def test_hud_coming_back_is_not_a_concede():
    FakeMenu.on_menu = False
    auto, asked = watcher()

    def deck_search_over():
        auto._last_hud_at = 210.0  # HUD seen again
        FakeMenu.on_menu = True
    run_watch(auto, deck_search_over)
    assert asked == []


def test_end_screen_handled_is_not_a_concede():
    FakeMenu.on_menu = False
    auto, asked = watcher()

    def end_screen():
        auto._battle_since = None  # the end screen was handled
        FakeMenu.on_menu = True
    run_watch(auto, end_screen)
    assert asked == []


def test_a_hud_blip_is_not_a_battle():
    # 24 Nov 2026: one HUD match on the deck editor, then a "menu": no question.
    FakeMenu.on_menu = True
    auto, asked = watcher()
    auto._battle_since, auto._last_hud_at = 100.0, 103.0
    t = threading.Thread(target=auto._watch_for_menu, args=(100.0, 103.0))
    t.start()
    t.join(3)
    FakeMenu.on_menu = False
    assert asked == [] and auto._battle_since is None


if __name__ == "__main__":
    failures = 0
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                try:
                    fn()
                    print(f"PASS {name}")
                except Exception as exc:
                    failures += 1
                    print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failures else 0)
