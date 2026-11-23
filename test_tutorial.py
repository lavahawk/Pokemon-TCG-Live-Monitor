"""The tutorial's example data: its own file, believable numbers, 7-3 today."""
import os
import shutil
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tutorial  # noqa: E402

TMP = tempfile.mkdtemp(prefix="tutorial_test_")


def test_demo_db_contents():
    path = os.path.join(TMP, "demo.db")
    db = tutorial.build_demo_db(path, now=datetime.now())
    assert db.db_path == path
    battles = db.get_recent_battles_with_ids(limit=1000)
    assert 50 <= len(battles) <= 100, len(battles)
    assert db.get_today_stats() == (7, 3), db.get_today_stats()
    decks = db.get_known_deck_names()
    assert decks[0] == tutorial.DEMO_DECK and tutorial.DEMO_DECK_2 in decks, decks
    assert db.get_current_rank() > 1200
    conn = db._connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM battles WHERE is_tournament=1").fetchone()[0] == 2
        latest = conn.execute("SELECT MAX(timestamp) FROM battles").fetchone()[0]
    finally:
        conn.close()
    assert latest <= datetime.now().strftime("%Y-%m-%d %H:%M:%S"), latest  # nothing in the future


def test_same_data_every_time():
    now = datetime(2026, 11, 22, 21, 0, 0)
    a = tutorial.build_demo_db(os.path.join(TMP, "a.db"), now=now)
    b = tutorial.build_demo_db(os.path.join(TMP, "b.db"), now=now)
    assert a.get_recent_battles_with_ids(limit=1000) == b.get_recent_battles_with_ids(limit=1000)


def test_steps_are_complete():
    for tab, _target, title, body in tutorial._steps():
        assert title and body and len(body) < 420, title
        assert "<" not in body, f"plain text only: {title}"


if __name__ == "__main__":
    passed = 0
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                passed += 1
                print(f"PASS {name}")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"{passed} passed")
