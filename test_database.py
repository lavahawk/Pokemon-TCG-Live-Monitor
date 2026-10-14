"""Tests for BattleDatabase on temp DB files (run: python test_database.py).

Every test builds its own database under a temp folder; the real
tcg_battles.db is never opened (DB_PATH and the constructor default are
redirected before anything else runs).
"""
import atexit
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TMP = tempfile.mkdtemp(prefix="ptcgl_test_db_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

import BattleDatabase as BDB

BDB.DB_PATH = os.path.join(TMP, "never_used.db")
BDB.BattleDatabase.__init__.__defaults__ = (BDB.DB_PATH, False)

_counter = [0]


def fresh(name=None):
    _counter[0] += 1
    return BDB.BattleDatabase(os.path.join(TMP, name or f"t{_counter[0]}.db"))


def rows(db, sql, params=()):
    conn = sqlite3.connect(db.db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def today():
    return datetime.now().strftime("%Y-%m-%d")


# ── schema ─────────────────────────────────────────────────────────────────
def test_fresh_schema_has_every_column_and_version():
    db = fresh()
    cols = {r[1] for r in rows(db, "PRAGMA table_info(battles)")}
    assert {"id", "timestamp", "my_deck", "opponent_deck", "result", "my_rank", "confidence", "deck_source",
            "log_file", "is_tournament", "chat_log", "log_hash", "weight", "import_id"} <= cols
    assert rows(db, "SELECT value FROM meta WHERE key='schema_version'") == [(str(BDB.SCHEMA_VERSION),)]
    indexes = {r[1] for r in rows(db, "PRAGMA index_list(battles)")}
    assert {"idx_battles_log_hash", "idx_battles_deck", "idx_battles_ts"} <= indexes
    BDB.BattleDatabase(db.db_path)  # reopening is a no-op
    assert rows(db, "SELECT COUNT(*) FROM meta") == [(1,)]


def test_migrates_v1_database():
    path = os.path.join(TMP, "v1.db")
    log_path = os.path.join(TMP, "battle_log_old.txt")
    with open(log_path, "w", encoding="cp1252", newline="") as handle:  # old logs are cp1252
        handle.write("Setup\r\nPokémon played.  \r\nme wins.\r\n")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE battles (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME, my_deck TEXT NOT NULL,
            opponent_deck TEXT NOT NULL, result TEXT NOT NULL, my_rank INTEGER, confidence INTEGER,
            deck_source TEXT, log_file TEXT);
        CREATE TABLE rank_history (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME,
            rank INTEGER NOT NULL, deck_name TEXT);
    """)
    utc = "2025-01-15 12:00:00"
    conn.executemany("INSERT INTO battles (timestamp, my_deck, opponent_deck, result, my_rank, log_file) "
                     "VALUES (?, ?, ?, ?, ?, ?)",
                     [(utc, "A", "B", "Win", 100, log_path), (utc, "A", "C", "Loss", 90, log_path),
                      (utc, "A", "D", "Loss", None, os.path.join(TMP, "missing.txt"))])
    for minute, rank in enumerate((151, 3, 151, 161, 20, 30)):  # 3 = OCR spike; 161 -> 20 -> 30 is real
        conn.execute("INSERT INTO rank_history (timestamp, rank) VALUES (?, ?)", (f"2025-01-15 12:{minute:02d}:00", rank))
    conn.commit()
    conn.close()

    db = BDB.BattleDatabase(path)
    expected = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    assert {r[0] for r in rows(db, "SELECT timestamp FROM battles")} == {expected}
    hashes = [r[0] for r in rows(db, "SELECT log_hash FROM battles ORDER BY id")]
    assert hashes[0] == BDB.log_hash("Setup\nPokémon played.\nme wins.")  # cp1252 log read, normalised
    assert hashes[1] is None and hashes[2] is None  # same log twice: first row wins; missing file: none
    assert [r[0] for r in rows(db, "SELECT rank FROM rank_history ORDER BY id")] == [151, 151, 161, 20, 30]
    assert rows(db, "SELECT value FROM meta WHERE key='schema_version'") == [("2",)]
    assert "is_tournament" in {r[1] for r in rows(db, "PRAGMA table_info(battles)")}
    # migrating is one-time: reopening doesn't shift timestamps again
    BDB.BattleDatabase(path)
    assert {r[0] for r in rows(db, "SELECT timestamp FROM battles")} == {expected}


def test_rank_spike_rule():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rank_history (id INTEGER PRIMARY KEY, timestamp TEXT, rank INTEGER)")
    for i, r in enumerate((30, 4, 30, 500, 520, 300, 515)):
        conn.execute("INSERT INTO rank_history VALUES (?, ?, ?)", (i + 1, f"t{i}", r))
    doomed = BDB.BattleDatabase._remove_rank_spikes(conn.cursor())
    assert doomed == [2, 6]  # 4 between 30s, 300 between 520/515


# ── hashing ────────────────────────────────────────────────────────────────
def test_log_hash_normalises_newlines_and_trailing_space():
    a = BDB.log_hash("Setup\r\nme drew a card.   \r\nme wins.\r\n\r\n")
    assert a == BDB.log_hash("Setup\nme drew a card.\nme wins.")
    assert a == BDB.log_hash("\n Setup\rme drew a card.\rme wins.".lstrip("\n "))
    assert a != BDB.log_hash("Setup\nme drew a card.\nopp wins.")
    assert BDB.log_hash("") is None and BDB.log_hash("  \r\n ") is None and BDB.log_hash(None) is None


# ── battles ────────────────────────────────────────────────────────────────
def test_add_battle_and_duplicate_log():
    db = fresh()
    h = BDB.log_hash("game one")
    first = db.add_battle("Gengar", "Dragapult", "Win", my_rank=120, confidence=80, log_hash=h, is_tournament=True)
    assert isinstance(first, int) and db.has_log_hash(h)
    assert db.add_battle("Gengar", "Other", "Loss", log_hash=h) is None  # same log: refused
    assert db.add_battle("Gengar", "Other", "Loss") and db.add_battle("Gengar", "Other", "Loss")  # no hash: allowed
    assert not db.has_log_hash(None) and not db.has_log_hash("nope")
    rec = rows(db, "SELECT my_deck, opponent_deck, result, my_rank, confidence, deck_source, is_tournament "
                   "FROM battles WHERE id=?", (first,))[0]
    assert rec == ("Gengar", "Dragapult", "Win", 120, 80, "AI", 1)
    assert db.get_today_stats() == (1, 2)
    assert db.get_known_deck_names() == ["Gengar"]


def test_update_battle_record_whitelist():
    db = fresh()
    bid = db.add_battle("Gengar", "Dragapult", "Loss", log_file="orig.txt")
    # non-editable columns are dropped (log_file, id, timestamp, a SQL-looking key)
    assert db.update_battle_record(bid, updates={"log_file": "x", "id": 99, "timestamp": "2000-01-01",
                                                 "result = 'Win', my_deck": "x"}) is False
    assert rows(db, "SELECT id, log_file, result, my_deck FROM battles") == [(bid, "orig.txt", "Loss", "Gengar")]
    # editable ones go through; `updates` wins over the same keyword
    assert db.update_battle_record(bid, updates={"opponent_deck": "Gardevoir", "log_file": "x"},
                                   opponent_deck="ignored", result="Win", confidence=0) is True
    assert rows(db, "SELECT opponent_deck, result, confidence, log_file FROM battles") == [("Gardevoir", "Win", 0, "orig.txt")]
    assert db.update_battle_record(bid, updates={"is_tournament": 1, "deck_source": "User"})
    assert rows(db, "SELECT is_tournament, deck_source FROM battles") == [(1, "User")]
    assert db.update_battle_record(bid + 100, result="Win") is False  # no such row
    assert db.update_battle_record(bid) is False  # nothing to change
    assert db.get_today_stats() == (1, 0)  # session stats rebuilt after the edit


def test_delete_battle_rebuilds_stats():
    db = fresh()
    a = db.add_battle("X", "Y", "Win")
    db.add_battle("X", "Y", "Loss")
    assert db.get_today_stats() == (1, 1)
    assert db.delete_battle(a) is True and db.delete_battle(a) is False
    assert db.get_today_stats() == (0, 1)


def test_reset_today_survives_rebuild_and_ignored_decks():
    db = fresh()
    db.add_battle("X", "Y", "Win")
    db.add_battle("Z", "Y", "Loss")
    db.reset_today_stats()
    assert db.get_today_stats() == (0, 0)
    # pretend the reset happened a minute ago, so games added now are after it
    earlier = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db.db_path)
    conn.execute("UPDATE session_resets SET reset_at=?", (earlier,))
    conn.execute("UPDATE battles SET timestamp=?", ((datetime.now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S"),))
    conn.commit()
    conn.close()
    later = db.add_battle("X", "Y", "Win")
    db.add_battle("Z", "Y", "Win")
    db.rebuild_session_stats()
    assert db.get_today_stats() == (2, 0)  # the pre-reset games stay out after a rebuild
    assert db.get_today_stats(ignored_decks=["Z", ""]) == (1, 0)
    assert db.update_battle_record(later, result="Loss")
    assert db.get_today_stats() == (1, 1)


def test_imported_results_stay_out_of_daily_views():
    db = fresh()
    db.add_battle("Gengar", "Dragapult", "Win", my_rank=200)
    iid = db.add_imported_record("Gengar", 3, 2, 1, 0.5, "2025-03-01", tournament=True, note="league cup")
    assert db.get_today_stats() == (1, 0)
    assert len(db.get_recent_battles_with_ids()) == 1 and len(db.get_recent_battles()) == 1
    assert db.get_deck_matchups("Gengar") == [("Dragapult", 1, 1, 0, 0)]
    assert len(db.get_battle_timeline()) == 1
    assert db.get_deck_stats("Gengar") == (7, 4, 2)  # imports count in deck stats
    assert db.get_all_time_stats()[:3] == (7, 4, 2)
    detailed = db.get_deck_battles_detailed("Gengar")
    assert sum(d["imported"] for d in detailed) == 6 and {d["weight"] for d in detailed if d["imported"]} == {0.5}
    assert db.list_imports() == [(iid, "2025-03-01", "Gengar", 3, 2, 1, 0.5, 1, "league cup")]
    db.rebuild_session_stats()
    assert rows(db, "SELECT date, wins, losses FROM session_stats") == [(today(), 1, 0)]
    assert db.delete_import(iid) == 6 and db.list_imports() == []


# ── ranks and queries ──────────────────────────────────────────────────────
def test_max_rank_ignores_one_off_readings():
    db = fresh()
    assert db.get_max_rank() is None and db.get_current_rank() is None
    for r in (120, 125, 900, 130):  # 900 = isolated misread
        db.add_rank_update(r, "Gengar")
    assert db.get_current_rank() == 130
    assert db.get_max_rank() == 130
    db.add_rank_update(900)
    assert db.get_max_rank() == 900  # read twice: real
    assert [r for _t, r in db.get_elo_history(limit=2)] == [130, 900]
    assert len(db.get_elo_history()) == 5


def test_data_signature_tracks_changes():
    db = fresh()
    s0 = db.data_signature()
    bid = db.add_battle("X", "Y", "Win")
    s1 = db.data_signature()
    db.update_battle_record(bid, opponent_deck="Z")
    s2 = db.data_signature()
    db.add_rank_update(50)
    s3 = db.data_signature()
    assert len({s0, s1, s2, s3}) == 4
    assert db.data_signature() == s3


def test_deck_queries():
    db = fresh()
    for opp, res, rank in (("A", "Win", 100), ("A", "Loss", 110), ("B", "Tie", None), ("A", "Win", 120)):
        db.add_battle("Mine", opp, res, my_rank=rank)
    db.add_battle("Other", "A", "Loss")
    assert db.get_deck_matchups("Mine") == [("A", 3, 2, 1, 0), ("B", 1, 0, 0, 1)]
    usage = {r[0]: r[1:5] for r in db.get_deck_usage_stats(limit=None)}
    assert usage == {"Mine": (4, 2, 1, 1), "Other": (1, 0, 1, 0)}
    assert [b["result"] for b in db.get_deck_battles_with_rank("Mine")] == ["Win", "Loss", "Tie", "Win"]
    assert len(db.get_deck_recent_battles("Mine", limit=2)) == 2
    assert [r[1] for r in db.get_deck_battle_history("Mine")] == ["Win", "Loss", "Tie", "Win"]
    wr = db.get_win_rate_over_time(days=7)
    assert wr == [(today(), 2, 2, 5)]
    assert db.get_all_time_stats() == (5, 2, 2, 120, 100)


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
