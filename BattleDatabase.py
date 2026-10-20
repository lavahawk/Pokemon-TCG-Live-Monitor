"""
SQLite database module for TCG Live Monitor.

v2.4 changes (see DevVault/03 Findings/Bug Register):
* Timestamps are stored in LOCAL time ("YYYY-MM-DD HH:MM:SS"). Older rows were
  UTC (SQLite CURRENT_TIMESTAMP); a one-time migration converts them (BUG-004).
* battles.log_hash (normalised SHA-256 of the battle log) with a UNIQUE index:
  the same log can never be stored twice (BUG-002).
* Isolated OCR rank spikes are removed from rank_history once (BUG-020) and
  max rank ignores one-off readings.
* get_all_time_stats counts every battle, not just ranked ones (BUG-024).
* Manual "reset today" survives session-stat rebuilds.
* Column whitelist for updates; every connection uses a busy timeout.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tcg_battles.db")

SCHEMA_VERSION = 2
EDITABLE_COLUMNS = {"my_deck", "opponent_deck", "result", "my_rank", "confidence", "deck_source", "is_tournament"}


def now_local():
    """Local wall-clock timestamp in the format stored in the DB."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_log_text(text):
    """Normalise a battle log so the same game always hashes the same."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def log_hash(text):
    normalized = normalize_log_text(text)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8", "ignore")).hexdigest()


def _read_log_file(path):
    for encoding in ("utf-8", "cp1252"):
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except UnicodeDecodeError:
            continue
        except Exception:
            return None
    return None


# Opponent placeholder for imported results (no matchup information).
IMPORTED_OPPONENT = "(imported result)"


class BattleDatabase:
    """Handles all database operations for battle tracking."""

    def __init__(self, db_path=DB_PATH, verbose=False):
        self.db_path = db_path
        self.verbose = verbose
        self.init_database()

    # ── connection ─────────────────────────────────────────────────────
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        return conn

    # ── schema ─────────────────────────────────────────────────────────
    def init_database(self):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS battles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    my_deck TEXT NOT NULL,
                    opponent_deck TEXT NOT NULL,
                    result TEXT NOT NULL,
                    my_rank INTEGER,
                    confidence INTEGER,
                    deck_source TEXT,
                    log_file TEXT,
                    is_tournament INTEGER DEFAULT 0,
                    chat_log TEXT,
                    log_hash TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rank_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    rank INTEGER NOT NULL,
                    deck_name TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS session_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE UNIQUE,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    max_rank INTEGER,
                    min_rank INTEGER
                )
            """)
            cur.execute("CREATE TABLE IF NOT EXISTS session_resets (date DATE PRIMARY KEY, reset_at DATETIME)")
            cur.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")

            columns = {row[1] for row in cur.execute("PRAGMA table_info(battles)")}
            # weight: an explicit per-game weight (imported results); import_id
            # groups the rows of one import so it can be removed as a whole.
            for name, ddl in (("is_tournament", "INTEGER DEFAULT 0"), ("chat_log", "TEXT"), ("log_hash", "TEXT"),
                              ("weight", "REAL"), ("import_id", "TEXT"), ("card_ranked", "TEXT")):
                if name not in columns:
                    cur.execute(f"ALTER TABLE battles ADD COLUMN {name} {ddl}")
            conn.commit()

            row = cur.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            version = int(row[0]) if row else 1
            if version < 2:
                # Exclusive write lock, then re-check: another process (overlay,
                # parser, dashboard) may have migrated meanwhile. Migrating twice
                # would shift the timestamps twice.
                cur.execute("BEGIN IMMEDIATE")
                row = cur.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                if (int(row[0]) if row else 1) < 2:
                    self._migrate_to_v2(conn)
                else:
                    conn.commit()
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_battles_log_hash ON battles(log_hash) WHERE log_hash IS NOT NULL")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_battles_deck ON battles(my_deck)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_battles_ts ON battles(timestamp)")
            conn.commit()
        finally:
            conn.close()
        if self.verbose:
            print(f"✓ Database initialized at {self.db_path}")

    def _migrate_to_v2(self, conn):
        """UTC -> local timestamps, log hashes, rank spike cleanup, rebuild."""
        cur = conn.cursor()
        # 1) Timestamps: every pre-v2 row was written by CURRENT_TIMESTAMP (UTC).
        cur.execute("UPDATE battles SET timestamp = datetime(timestamp, 'localtime') WHERE timestamp IS NOT NULL")
        cur.execute("UPDATE rank_history SET timestamp = datetime(timestamp, 'localtime') WHERE timestamp IS NOT NULL")

        # 2) Backfill log hashes from the saved log files (first row wins).
        seen = set()
        for battle_id, path in cur.execute("SELECT id, log_file FROM battles ORDER BY id").fetchall():
            resolved = self._resolve_log_path(path)
            text = _read_log_file(resolved) if resolved else None
            digest = log_hash(text) if text else None
            if digest and digest not in seen:
                seen.add(digest)
                cur.execute("UPDATE battles SET log_hash=? WHERE id=?", (digest, battle_id))

        # 3) Drop isolated OCR spikes from rank history.
        self._remove_rank_spikes(cur)

        cur.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.commit()
        self._rebuild_session_stats(conn)

    def _resolve_log_path(self, path):
        if not path:
            return None
        if os.path.exists(path):
            return path
        candidate = os.path.join(BASE_DIR, "Logs", os.path.basename(path.replace("\\", "/")))
        return candidate if os.path.exists(candidate) else None

    @staticmethod
    def _remove_rank_spikes(cur, neighbour_tolerance=20):
        """Delete single readings that disagree with two agreeing neighbours.

        e.g. 151, 3, 151 or 30, 4, 30 (dropped digits). A real change such as
        a season reset (161 -> 20 -> 30) has disagreeing neighbours and stays.
        """
        rows = cur.execute("SELECT id, rank FROM rank_history ORDER BY timestamp, id").fetchall()
        doomed = []
        for i in range(1, len(rows) - 1):
            prev_rank, rank, next_rank = rows[i - 1][1], rows[i][1], rows[i + 1][1]
            jump = max(15, 0.4 * (prev_rank + next_rank) / 2.0)
            if (abs(prev_rank - next_rank) <= neighbour_tolerance
                    and abs(rank - prev_rank) > jump and abs(rank - next_rank) > jump):
                doomed.append(rows[i][0])
        for rid in doomed:
            cur.execute("DELETE FROM rank_history WHERE id=?", (rid,))
        return doomed

    # ── battles ────────────────────────────────────────────────────────
    def has_log_hash(self, digest):
        if not digest:
            return False
        conn = self._connect()
        try:
            return conn.execute("SELECT 1 FROM battles WHERE log_hash=? LIMIT 1", (digest,)).fetchone() is not None
        finally:
            conn.close()

    def add_battle(self, my_deck, opponent_deck, result, my_rank=None, confidence=None,
                   deck_source="AI", log_file=None, is_tournament=False, chat_log=None, log_hash=None,
                   card_ranked=None):
        """Add a battle. Returns the new id, or None if this log is already stored.
        card_ranked: [(archetype, probability)] from the opponent's revealed
        cards (card_usage.classify), a second opinion on the label."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO battles (timestamp, my_deck, opponent_deck, result, my_rank, confidence,
                                         deck_source, log_file, is_tournament, chat_log, log_hash, card_ranked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (now_local(), my_deck, opponent_deck, result, my_rank, confidence, deck_source,
                      log_file, 1 if is_tournament else 0, chat_log, log_hash,
                      json.dumps([[str(d), round(float(p), 4)] for d, p in card_ranked]) if card_ranked else None))
            except sqlite3.IntegrityError:
                return None  # duplicate log
            battle_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        self.update_session_stats(result, my_rank)
        return battle_id

    def update_battle_record(self, battle_id, *, updates=None, my_deck=None, opponent_deck=None,
                             result=None, my_rank=None, confidence=None, deck_source=None):
        fields = dict(updates or {})
        for key, value in (("my_deck", my_deck), ("opponent_deck", opponent_deck), ("result", result),
                           ("my_rank", my_rank), ("confidence", confidence), ("deck_source", deck_source)):
            if value is not None and key not in fields:
                fields[key] = value
        fields = {k: v for k, v in fields.items() if k in EDITABLE_COLUMNS}
        if not fields:
            return False
        assignments = ", ".join(f"{column} = ?" for column in fields)
        conn = self._connect()
        try:
            cur = conn.execute(f"UPDATE battles SET {assignments} WHERE id = ?", list(fields.values()) + [battle_id])
            changed = cur.rowcount > 0
            conn.commit()
        finally:
            conn.close()
        if changed:
            self.rebuild_session_stats()
        return changed

    def delete_battle(self, battle_id):
        conn = self._connect()
        try:
            changed = conn.execute("DELETE FROM battles WHERE id = ?", (battle_id,)).rowcount > 0
            conn.commit()
        finally:
            conn.close()
        if changed:
            self.rebuild_session_stats()
        return changed

    def get_known_deck_names(self):
        conn = self._connect()
        try:
            rows = conn.execute("SELECT my_deck, COUNT(*) c FROM battles GROUP BY my_deck ORDER BY c DESC").fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows if r[0]]

    # ── ranks ──────────────────────────────────────────────────────────
    def add_rank_update(self, rank, deck_name=None):
        conn = self._connect()
        try:
            conn.execute("INSERT INTO rank_history (timestamp, rank, deck_name) VALUES (?, ?, ?)",
                         (now_local(), rank, deck_name))
            conn.commit()
        finally:
            conn.close()

    def get_current_rank(self):
        conn = self._connect()
        try:
            row = conn.execute("SELECT rank FROM rank_history ORDER BY timestamp DESC, id DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        return row[0] if row else None

    def data_signature(self):
        """Cheap fingerprint of everything the dashboard displays.

        Changes whenever a battle or rank reading is added, edited or
        deleted, so the dashboard can skip its 15 s refresh when nothing
        changed (that refresh rebuilt every deck analysis and graph).
        """
        conn = self._connect()
        try:
            battles = conn.execute(
                "SELECT COUNT(*), group_concat(id || '|' || COALESCE(timestamp,'') || '|' || COALESCE(my_deck,'') || '|' || "
                "COALESCE(opponent_deck,'') || '|' || COALESCE(result,'') || '|' || COALESCE(my_rank,'') || '|' || "
                "COALESCE(is_tournament,''), ';') FROM battles").fetchone()
            ranks = conn.execute("SELECT COUNT(*), MAX(id), SUM(rank) FROM rank_history").fetchone()
        finally:
            conn.close()
        return (battles[0], hash(battles[1] or ""), tuple(ranks))

    def get_max_rank(self, near=150):
        """Best rank, ignoring isolated one-off misreads.

        A rank counts when it was read at least twice, or when another
        reading lies within `near` of it. (Requiring two identical reads
        froze the max in Master league, where the points change after
        every game and the same value rarely repeats.)
        """
        conn = self._connect()
        try:
            values = [r[0] for r in conn.execute(
                "SELECT rank FROM rank_history WHERE rank IS NOT NULL UNION ALL "
                "SELECT my_rank FROM battles WHERE my_rank IS NOT NULL")]
        finally:
            conn.close()
        from collections import Counter
        counts = Counter(values)
        distinct = sorted(counts)
        best = None
        for i, v in enumerate(distinct):
            supported = counts[v] >= 2 or any(
                abs(v - w) <= near for w in distinct[max(0, i - 1):i + 2] if w != v)
            if supported and (best is None or v > best):
                best = v
        return best

    def get_elo_history(self, limit=None):
        conn = self._connect()
        try:
            query = "SELECT timestamp, rank FROM rank_history ORDER BY timestamp DESC, id DESC"
            params = ()
            if limit is not None:
                query += " LIMIT ?"
                params = (limit,)
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()
        return list(reversed(rows)) if rows else []

    # ── session stats ──────────────────────────────────────────────────
    def update_session_stats(self, result, rank=None):
        today = datetime.now().strftime("%Y-%m-%d")
        res = (result or "").upper()
        conn = self._connect()
        try:
            cur = conn.cursor()
            row = cur.execute("SELECT wins, losses, max_rank, min_rank FROM session_stats WHERE date = ?", (today,)).fetchone()
            if row:
                wins = row[0] + (1 if res == "WIN" else 0)
                losses = row[1] + (1 if res == "LOSS" else 0)
                max_rank, min_rank = row[2], row[3]
                if rank:
                    max_rank = rank if max_rank is None or rank > max_rank else max_rank
                    min_rank = rank if min_rank is None or rank < min_rank else min_rank
                cur.execute("UPDATE session_stats SET wins=?, losses=?, max_rank=?, min_rank=? WHERE date=?",
                            (wins, losses, max_rank, min_rank, today))
            else:
                cur.execute("INSERT INTO session_stats (date, wins, losses, max_rank, min_rank) VALUES (?, ?, ?, ?, ?)",
                            (today, 1 if res == "WIN" else 0, 1 if res == "LOSS" else 0, rank, rank))
            conn.commit()
        finally:
            conn.close()

    def rebuild_session_stats(self):
        conn = self._connect()
        try:
            self._rebuild_session_stats(conn)
        finally:
            conn.close()

    @staticmethod
    def _rebuild_session_stats(conn):
        cur = conn.cursor()
        resets = dict(cur.execute("SELECT date, reset_at FROM session_resets").fetchall())
        cur.execute("DELETE FROM session_stats")
        rows = cur.execute("""
            SELECT DATE(timestamp), timestamp, upper(result), my_rank FROM battles
            WHERE COALESCE(deck_source, '') != 'Import' ORDER BY timestamp
        """).fetchall()
        days = {}
        for day, ts, result, rank in rows:
            if day is None:
                continue
            stats = days.setdefault(day, [0, 0, None, None])
            if day in resets and ts and ts <= resets[day]:
                continue
            stats[0] += result == "WIN"
            stats[1] += result == "LOSS"
            if rank is not None:
                stats[2] = rank if stats[2] is None else max(stats[2], rank)
                stats[3] = rank if stats[3] is None else min(stats[3], rank)
        for day, (wins, losses, max_rank, min_rank) in sorted(days.items()):
            cur.execute("INSERT INTO session_stats (date, wins, losses, max_rank, min_rank) VALUES (?, ?, ?, ?, ?)",
                        (day, wins, losses, max_rank, min_rank))
        conn.commit()

    def get_today_stats(self, ignored_decks=None):
        """Today's W-L (since the last reset). Games with an ignored deck
        (Decks → Ignore) are left out."""
        today = datetime.now().strftime("%Y-%m-%d")
        conn = self._connect()
        try:
            row = conn.execute("SELECT wins, losses FROM session_stats WHERE date = ?", (today,)).fetchone()
            wins, losses = (row[0], row[1]) if row else (0, 0)
            ignored = [d for d in (ignored_decks or []) if d]
            if ignored and (wins or losses):
                reset = conn.execute("SELECT reset_at FROM session_resets WHERE date = ?", (today,)).fetchone()
                marks = ",".join("?" * len(ignored))
                skip_w, skip_l = conn.execute(
                    f"SELECT SUM(upper(result) = 'WIN'), SUM(upper(result) = 'LOSS') FROM battles "
                    f"WHERE DATE(timestamp) = ? AND timestamp > ? AND COALESCE(deck_source, '') != 'Import' "
                    f"AND my_deck IN ({marks})",
                    [today, reset[0] if reset and reset[0] else ""] + ignored).fetchone()
                wins = max(0, wins - (skip_w or 0))
                losses = max(0, losses - (skip_l or 0))
        finally:
            conn.close()
        return wins, losses

    def reset_today_stats(self):
        """Reset today's W/L to 0-0 (battle history is untouched; survives rebuilds)."""
        today = datetime.now().strftime("%Y-%m-%d")
        conn = self._connect()
        try:
            conn.execute("INSERT OR REPLACE INTO session_resets(date, reset_at) VALUES (?, ?)", (today, now_local()))
            conn.execute("UPDATE session_stats SET wins = 0, losses = 0 WHERE date = ?", (today,))
            conn.commit()
        finally:
            conn.close()
        return True

    # ── imported results (Advanced → Import your results) ──────────────
    def add_imported_record(self, deck, wins, losses, ties, weight, date, *, tournament=False, note=""):
        """Add results played before / outside the app as one game row each
        (opponent unknown), with an explicit per-game weight. They count in
        deck statistics and the Score, not in today's W-L, the charts,
        Recent Battles or matchups. Returns the import id."""
        import uuid
        import_id = uuid.uuid4().hex[:12]
        stamp = f"{date} 12:00:00"
        rows = ([("Win",)] * int(wins) + [("Loss",)] * int(losses) + [("Tie",)] * int(ties))
        conn = self._connect()
        try:
            conn.executemany(
                "INSERT INTO battles (timestamp, my_deck, opponent_deck, result, my_rank, confidence, deck_source, "
                "log_file, is_tournament, weight, import_id) VALUES (?, ?, ?, ?, NULL, 100, 'Import', ?, ?, ?, ?)",
                [(stamp, deck, IMPORTED_OPPONENT, r[0], (note or "")[:200], 1 if tournament else 0, float(weight),
                  import_id) for r in rows])
            conn.commit()
        finally:
            conn.close()
        return import_id

    def list_imports(self):
        """[(import_id, date, deck, wins, losses, ties, weight, tournament, note)] newest first."""
        return self._fetchall("""
            SELECT import_id, DATE(MIN(timestamp)), my_deck,
                   SUM(CASE WHEN result='Win' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN result='Loss' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN lower(result) IN ('tie','draw') THEN 1 ELSE 0 END),
                   MAX(weight), MAX(is_tournament), MAX(log_file)
            FROM battles WHERE deck_source = 'Import' AND import_id IS NOT NULL
            GROUP BY import_id ORDER BY MIN(id) DESC
        """)

    def delete_import(self, import_id):
        conn = self._connect()
        try:
            changed = conn.execute("DELETE FROM battles WHERE deck_source = 'Import' AND import_id = ?",
                                   (import_id,)).rowcount
            conn.commit()
        finally:
            conn.close()
        return changed

    # ── queries for the UI ─────────────────────────────────────────────
    def _fetchall(self, query, params=()):
        conn = self._connect()
        try:
            return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    def get_recent_battles_with_ids(self, limit=20):
        return self._fetchall("""
            SELECT id, timestamp, my_deck, opponent_deck, result, my_rank, confidence, deck_source, log_file, is_tournament
            FROM battles WHERE COALESCE(deck_source, '') != 'Import' ORDER BY timestamp DESC, id DESC LIMIT ?
        """, (limit,))

    def get_recent_battles(self, limit=10):
        return self._fetchall("""
            SELECT timestamp, my_deck, opponent_deck, result, my_rank, log_file, is_tournament
            FROM battles WHERE COALESCE(deck_source, '') != 'Import' ORDER BY timestamp DESC, id DESC LIMIT ?
        """, (limit,))

    def get_deck_stats(self, deck_name):
        row = self._fetchall("""
            SELECT COUNT(*), SUM(CASE WHEN result='Win' THEN 1 ELSE 0 END), SUM(CASE WHEN result='Loss' THEN 1 ELSE 0 END)
            FROM battles WHERE my_deck = ?
        """, (deck_name,))
        return row[0] if row else (0, 0, 0)

    def get_all_time_stats(self):
        """(total, wins, losses, best_rank, worst_rank) over ALL battles."""
        rows = self._fetchall("""
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN result='Win' THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN result='Loss' THEN 1 ELSE 0 END), 0),
                   MAX(my_rank), MIN(my_rank)
            FROM battles
        """)
        total, wins, losses, best_rank, worst_rank = rows[0] if rows else (0, 0, 0, None, None)
        history_max = self.get_max_rank()
        if history_max and (not best_rank or history_max > best_rank):
            best_rank = history_max
        return (total, wins, losses, best_rank, worst_rank)

    def get_win_rate_over_time(self, days=30):
        return self._fetchall("""
            SELECT DATE(timestamp) AS d,
                   SUM(CASE WHEN result='Win' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN result='Loss' THEN 1 ELSE 0 END),
                   COUNT(*)
            FROM battles
            WHERE timestamp >= date('now', 'localtime', '-' || ? || ' days') AND COALESCE(deck_source, '') != 'Import'
            GROUP BY DATE(timestamp) ORDER BY d ASC
        """, (days,))

    def get_deck_usage_stats(self, limit=10):
        query = """
            SELECT my_deck, COUNT(*),
                   SUM(CASE WHEN result='Win' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN result='Loss' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN lower(result) IN ('tie','draw') THEN 1 ELSE 0 END),
                   MAX(timestamp) AS last_played
            FROM battles GROUP BY my_deck ORDER BY last_played DESC, COUNT(*) DESC
        """
        params = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        return self._fetchall(query, params)

    def get_deck_matchups(self, deck_name):
        return self._fetchall("""
            SELECT opponent_deck, COUNT(*) AS games,
                   SUM(CASE WHEN result='Win' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN result='Loss' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN lower(result) IN ('tie','draw') THEN 1 ELSE 0 END)
            FROM battles WHERE my_deck = ? AND COALESCE(deck_source, '') != 'Import'
            GROUP BY opponent_deck ORDER BY games DESC, wins DESC, opponent_deck ASC
        """, (deck_name,))

    def get_deck_recent_battles(self, deck_name, limit=8):
        return self._fetchall("""
            SELECT timestamp, my_deck, opponent_deck, result, my_rank, log_file, is_tournament
            FROM battles WHERE my_deck = ? AND COALESCE(deck_source, '') != 'Import' ORDER BY timestamp DESC, id DESC LIMIT ?
        """, (deck_name, limit))

    def get_deck_battle_history(self, deck_name):
        return self._fetchall("SELECT timestamp, result FROM battles WHERE my_deck = ? AND COALESCE(deck_source, '') != 'Import' "
                              "ORDER BY timestamp ASC", (deck_name,))

    def get_deck_battles_with_rank(self, deck_name):
        rows = self._fetchall("SELECT result, my_rank, is_tournament FROM battles WHERE my_deck = ? ORDER BY timestamp ASC", (deck_name,))
        return [{"result": str(r or "").strip(), "my_rank": rank, "is_tournament": bool(t)} for r, rank, t in rows]

    def get_deck_battles_detailed(self, deck_name):
        """Every game with this deck: result, rank, tournament flag, date, opponent."""
        rows = self._fetchall(
            "SELECT result, my_rank, is_tournament, timestamp, opponent_deck, weight, deck_source, "
            "log_file, log_hash, card_ranked, "
            # rank going INTO the game: the previous battle's (any deck) rank
            "(SELECT p.my_rank FROM battles p WHERE p.my_rank IS NOT NULL AND "
            " (p.timestamp < b.timestamp OR (p.timestamp = b.timestamp AND p.id < b.id)) "
            " ORDER BY p.timestamp DESC, p.id DESC LIMIT 1) "
            "FROM battles b WHERE my_deck = ? ORDER BY timestamp ASC", (deck_name,))
        out = []
        for r, rank, t, ts, opp, w, src, log_file, lh, ranked, before in rows:
            try:
                ranked = [(str(d), float(p)) for d, p in json.loads(ranked)] if ranked else None
            except (ValueError, TypeError):
                ranked = None
            out.append({"result": str(r or "").strip(), "my_rank": rank, "is_tournament": bool(t),
                        "timestamp": ts, "opponent": opp, "weight": w, "imported": src == "Import",
                        "source": src or "", "log_file": log_file, "log_hash": lh, "card_ranked": ranked,
                        "rank_before": before})
        return out

    def get_battle_timeline(self):
        """Every battle oldest first: (timestamp, my_deck, opponent_deck, result, my_rank, is_tournament)."""
        return self._fetchall("SELECT timestamp, my_deck, opponent_deck, result, my_rank, is_tournament "
                              "FROM battles WHERE COALESCE(deck_source, '') != 'Import' ORDER BY timestamp ASC, id ASC")

    def get_all_battles_with_rank(self):
        rows = self._fetchall("SELECT my_deck, result, my_rank, is_tournament FROM battles ORDER BY timestamp ASC")
        return [{"my_deck": str(d or "").strip(), "result": str(r or "").strip(), "my_rank": rank, "is_tournament": bool(t)}
                for d, r, rank, t in rows]


if __name__ == "__main__":
    db = BattleDatabase(verbose=True)
    wins, losses = db.get_today_stats()
    print(f"Today: {wins}-{losses}")
    print(f"Rank: {db.get_current_rank()} | Max: {db.get_max_rank()}")
