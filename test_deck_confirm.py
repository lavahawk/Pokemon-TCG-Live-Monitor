"""Tests for deck_confirm: autocomplete ranking and the manual-mode request
(run: python test_deck_confirm.py). Files are redirected to a temp dir."""
import atexit
import json
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deck_confirm as C

TMP = tempfile.mkdtemp(prefix="deck_confirm_test_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
C.LIMITLESS_CACHE_FILE = os.path.join(TMP, "meta.json")
C.REQUEST_FILE = os.path.join(TMP, ".deck_confirm.json")


class FakeDB:
    def __init__(self, rows):
        self.path = os.path.join(TMP, "battles.db")
        conn = sqlite3.connect(self.path)
        conn.execute("DROP TABLE IF EXISTS battles")
        conn.execute("CREATE TABLE battles (opponent_deck TEXT)")
        conn.executemany("INSERT INTO battles VALUES (?)", [(r,) for r in rows])
        conn.commit()
        conn.close()

    def _connect(self):
        return sqlite3.connect(self.path)


def _meta(rows):
    with open(C.LIMITLESS_CACHE_FILE, "w", encoding="utf-8") as handle:
        json.dump({"rows": rows}, handle)


def test_meta_decks_first_by_share_then_faced():
    _meta([{"deck": "Gardevoir", "share": 3.0}, {"deck": "Dragapult", "share": 7.4}])
    db = FakeDB(["Gardevoir", "Gardevoir", "Homebrew", "Unknown (local mode)", "Rogue", "Rogue", "Rogue"])
    rows = C.deck_suggestions(db)
    assert [r[0] for r in rows] == ["Dragapult", "Gardevoir", "Rogue", "Homebrew"]
    assert rows[0][1] == 7.4 and rows[1][2] == 2 and rows[2] == ("Rogue", None, 3)


def test_suggestions_without_meta_or_db():
    if os.path.exists(C.LIMITLESS_CACHE_FILE):
        os.remove(C.LIMITLESS_CACHE_FILE)
    assert C.deck_suggestions(None) == []


def test_manual_request_is_stored():
    C.write_request(7, "Alakazam", source="guess", needs_input=True, result="Win",
                    candidates=[("Alakazam", 0.9)], manual="no_key")
    with open(C.REQUEST_FILE, encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["manual"] == "no_key" and data["needs_input"] is True
    assert data["candidates"] == [{"deck": "Alakazam", "p": 0.9}]


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
