"""
SQLite Database Module for TCG Live Monitor
Stores battle data for easy querying and statistics
"""

import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tcg_battles.db")


class BattleDatabase:
    """Handles all database operations for battle tracking"""
    
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Battles table - stores each battle result
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS battles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                my_deck TEXT NOT NULL,
                opponent_deck TEXT NOT NULL,
                result TEXT NOT NULL,
                my_rank INTEGER,
                confidence INTEGER,
                deck_source TEXT,
                log_file TEXT,
                is_tournament INTEGER DEFAULT 0
            )
        """)

        # Add is_tournament column to existing databases (migration).
        try:
            cursor.execute("PRAGMA table_info(battles)")
            columns = [row[1] for row in cursor.fetchall()]
            if "is_tournament" not in columns:
                cursor.execute("ALTER TABLE battles ADD COLUMN is_tournament INTEGER DEFAULT 0")
        except Exception:
            pass
        
        # Rank history table - tracks rank changes over time
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rank_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                rank INTEGER NOT NULL,
                deck_name TEXT
            )
        """)
        
        # Session stats table - daily/session summaries
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                max_rank INTEGER,
                min_rank INTEGER
            )
        """)
        
        conn.commit()
        conn.close()
        print(f"✓ Database initialized at {self.db_path}")
    
    def add_battle(self, my_deck, opponent_deck, result, my_rank=None, confidence=None, 
                   deck_source="AI", log_file=None, is_tournament=False):
        """Add a new battle record"""
        print(f"[DB] add_battle called: {my_deck} vs {opponent_deck} = {result}, Rank: {my_rank}, Tournament: {is_tournament}")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO battles (my_deck, opponent_deck, result, my_rank, confidence, deck_source, log_file, is_tournament)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (my_deck, opponent_deck, result, my_rank, confidence, deck_source, log_file, 1 if is_tournament else 0))
        
        battle_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Update session stats
        self.update_session_stats(result, my_rank)
        
        return battle_id

    def rebuild_session_stats(self):
        """Recalculate session stats from the battles table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM session_stats")
        cursor.execute("""
            SELECT
                DATE(timestamp) as battle_date,
                SUM(CASE WHEN upper(result) = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN upper(result) = 'LOSS' THEN 1 ELSE 0 END) as losses,
                MAX(my_rank) as max_rank,
                MIN(my_rank) as min_rank
            FROM battles
            GROUP BY DATE(timestamp)
            ORDER BY battle_date ASC
        """)
        rows = cursor.fetchall()

        for battle_date, wins, losses, max_rank, min_rank in rows:
            cursor.execute("""
                INSERT INTO session_stats (date, wins, losses, max_rank, min_rank)
                VALUES (?, ?, ?, ?, ?)
            """, (battle_date, wins or 0, losses or 0, max_rank, min_rank))

        conn.commit()
        conn.close()

    def get_recent_battles_with_ids(self, limit=20):
        """Get recent battle records including identifiers and editable metadata."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, timestamp, my_deck, opponent_deck, result, my_rank, confidence, deck_source, log_file, is_tournament
            FROM battles
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()
        return rows if rows else []

    def update_battle_record(
        self,
        battle_id,
        *,
        updates=None,
        my_deck=None,
        opponent_deck=None,
        result=None,
        my_rank=None,
        confidence=None,
        deck_source=None,
    ):
        """Update editable fields for a battle and rebuild session stats."""
        update_fields = dict(updates or {})
        if my_deck is not None:
            update_fields["my_deck"] = my_deck
        if opponent_deck is not None:
            update_fields["opponent_deck"] = opponent_deck
        if result is not None:
            update_fields["result"] = result
        if "my_rank" not in update_fields and my_rank is not None:
            update_fields["my_rank"] = my_rank
        if "confidence" not in update_fields and confidence is not None:
            update_fields["confidence"] = confidence
        if deck_source is not None:
            update_fields["deck_source"] = deck_source

        if not update_fields:
            return False

        assignments = ", ".join(f"{column} = ?" for column in update_fields.keys())
        values = list(update_fields.values()) + [battle_id]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE battles SET {assignments} WHERE id = ?", values)
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if changed:
            self.rebuild_session_stats()
        return changed

    def delete_battle(self, battle_id):
        """Delete a battle and rebuild session stats."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM battles WHERE id = ?", (battle_id,))
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if changed:
            self.rebuild_session_stats()
        return changed
    
    def add_rank_update(self, rank, deck_name=None):
        """Record a rank change"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO rank_history (rank, deck_name)
            VALUES (?, ?)
        """, (rank, deck_name))
        
        conn.commit()
        conn.close()
    
    def update_session_stats(self, result, rank=None):
        """Update today's session statistics"""
        today = datetime.now().date()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get or create today's stats
        cursor.execute("SELECT * FROM session_stats WHERE date = ?", (today,))
        row = cursor.fetchone()
        
        if row:
            # Update existing
            old_wins, old_losses = row[2], row[3]
            wins = row[2] + (1 if result.upper() == "WIN" else 0)
            losses = row[3] + (1 if result.upper() == "LOSS" else 0)
            max_rank = row[4]
            min_rank = row[5]
            
            if rank:
                # Higher Elo number = better (update max if rank is higher)
                if max_rank is None or rank > max_rank:
                    max_rank = rank
                if min_rank is None or rank < min_rank:
                    min_rank = rank
            
            cursor.execute("""
                UPDATE session_stats 
                SET wins = ?, losses = ?, max_rank = ?, min_rank = ?
                WHERE date = ?
            """, (wins, losses, max_rank, min_rank, today))
            print(f"✓ Session stats updated: {old_wins}-{old_losses} → {wins}-{losses}")
        else:
            # Create new
            wins = 1 if result.upper() == "WIN" else 0
            losses = 1 if result.upper() == "LOSS" else 0
            cursor.execute("""
                INSERT INTO session_stats (date, wins, losses, max_rank, min_rank)
                VALUES (?, ?, ?, ?, ?)
            """, (today, wins, losses, rank, rank))
            print(f"✓ Session stats created: {wins}-{losses}")
        
        conn.commit()
        conn.close()
    
    def get_today_stats(self):
        """Get today's win/loss record"""
        today = datetime.now().date()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT wins, losses FROM session_stats WHERE date = ?", (today,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return row[0], row[1]  # wins, losses
        return 0, 0
    
    def get_current_rank(self):
        """Get most recent rank"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT rank FROM rank_history ORDER BY timestamp DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def get_max_rank(self):
        """Get best rank ever (highest Elo number)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT MAX(rank) FROM rank_history")
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row and row[0] else None
    
    def get_recent_battles(self, limit=10):
        """Get recent battle records"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, my_deck, opponent_deck, result, my_rank, log_file, is_tournament
            FROM battles
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return rows
    
    def get_deck_stats(self, deck_name):
        """Get win/loss record for a specific deck"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses
            FROM battles
            WHERE my_deck = ?
        """, (deck_name,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row if row else (0, 0, 0)
    
    def get_all_time_stats(self):
        """Get overall statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_battles,
                SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as total_wins,
                SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as total_losses,
                MAX(my_rank) as best_rank,
                MIN(my_rank) as worst_rank
            FROM battles
            WHERE my_rank IS NOT NULL
        """)
        
        row = cursor.fetchone()
        
        # Also check rank_history for max rank (in case it's higher)
        cursor.execute("SELECT MAX(rank) FROM rank_history")
        max_from_history = cursor.fetchone()[0]
        
        conn.close()
        
        # Use the higher of the two max ranks
        if row:
            total, wins, losses, best_rank, worst_rank = row
            if max_from_history and (not best_rank or max_from_history > best_rank):
                best_rank = max_from_history
            return (total, wins, losses, best_rank, worst_rank)
        
        return (0, 0, 0, None, None)
    
    def get_elo_history(self, limit=None):
        """Get Elo progression over time"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT timestamp, rank
            FROM rank_history
            ORDER BY timestamp DESC
        """
        params = ()
        if limit is not None:
            query += "\nLIMIT ?"
            params = (limit,)

        cursor.execute(query, params)
        
        rows = cursor.fetchall()
        conn.close()
        
        # Return in chronological order (oldest first)
        return list(reversed(rows)) if rows else []
    
    def get_win_rate_over_time(self, days=30):
        """Get daily win rates for the past N days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                DATE(timestamp) as date,
                SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                COUNT(*) as total
            FROM battles
            WHERE timestamp >= date('now', '-' || ? || ' days')
            GROUP BY DATE(timestamp)
            ORDER BY date ASC
        """, (days,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return rows if rows else []
    
    def get_deck_usage_stats(self, limit=10):
        """Get deck usage statistics for decks you have played."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT 
                my_deck,
                COUNT(*) as games_played,
                SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN lower(result) IN ('tie', 'draw') THEN 1 ELSE 0 END) as ties
            FROM battles
            GROUP BY my_deck
            ORDER BY games_played DESC
        """
        params = ()
        if limit is not None:
            query += "\nLIMIT ?"
            params = (limit,)

        cursor.execute(query, params)

        rows = cursor.fetchall()
        conn.close()

        return rows if rows else []

    def get_deck_matchups(self, deck_name):
        """Get opponent matchup stats for one of your decks."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                opponent_deck,
                COUNT(*) as games_played,
                SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN lower(result) IN ('tie', 'draw') THEN 1 ELSE 0 END) as ties
            FROM battles
            WHERE my_deck = ?
            GROUP BY opponent_deck
            ORDER BY games_played DESC, wins DESC, opponent_deck ASC
        """, (deck_name,))

        rows = cursor.fetchall()
        conn.close()

        return rows if rows else []

    def get_deck_recent_battles(self, deck_name, limit=8):
        """Get recent battles played with a specific deck."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT timestamp, my_deck, opponent_deck, result, my_rank, log_file, is_tournament
            FROM battles
            WHERE my_deck = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (deck_name, limit))

        rows = cursor.fetchall()
        conn.close()

        return rows if rows else []

    def get_deck_battle_history(self, deck_name):
        """Get full chronological battle history for a specific deck."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT timestamp, result
            FROM battles
            WHERE my_deck = ?
            ORDER BY timestamp ASC
        """, (deck_name,))

        rows = cursor.fetchall()
        conn.close()

        return rows if rows else []

    def get_deck_battles_with_rank(self, deck_name):
        """Get per-battle results WITH their recorded rank (Elo) for a deck.

        Returns a list of dicts: {result, my_rank, is_tournament}. Battles
        without a recorded rank are included with my_rank=None so callers can
        decide how to treat them (e.g. fall back to a neutral weight).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT result, my_rank, is_tournament
            FROM battles
            WHERE my_deck = ?
            ORDER BY timestamp ASC
        """, (deck_name,))

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "result": str(result or "").strip(),
                "my_rank": my_rank,
                "is_tournament": bool(is_tournament),
            }
            for result, my_rank, is_tournament in rows
        ]

    def get_all_battles_with_rank(self):
        """Get every battle's result and rank across all decks.

        Returns a list of dicts: {my_deck, result, my_rank, is_tournament}.
        Used for the overall rank-weighted win rate.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT my_deck, result, my_rank, is_tournament
            FROM battles
            ORDER BY timestamp ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "my_deck": str(my_deck or "").strip(),
                "result": str(result or "").strip(),
                "my_rank": my_rank,
                "is_tournament": bool(is_tournament),
            }
            for my_deck, result, my_rank, is_tournament in rows
        ]


if __name__ == "__main__":
    # Test the database
    db = BattleDatabase()
    print("Database created successfully!")
    
    # Show stats
    wins, losses = db.get_today_stats()
    print(f"Today: {wins}-{losses}")
    
    current_rank = db.get_current_rank()
    max_rank = db.get_max_rank()
    print(f"Rank: {current_rank} | Max: {max_rank}")
