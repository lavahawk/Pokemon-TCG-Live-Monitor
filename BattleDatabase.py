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
                log_file TEXT
            )
        """)
        
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
                   deck_source="AI", log_file=None):
        """Add a new battle record"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO battles (my_deck, opponent_deck, result, my_rank, confidence, deck_source, log_file)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (my_deck, opponent_deck, result, my_rank, confidence, deck_source, log_file))
        
        battle_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Update session stats
        self.update_session_stats(result, my_rank)
        
        return battle_id
    
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
        else:
            # Create new
            cursor.execute("""
                INSERT INTO session_stats (date, wins, losses, max_rank, min_rank)
                VALUES (?, ?, ?, ?, ?)
            """, (today, 
                  1 if result.upper() == "WIN" else 0,
                  1 if result.upper() == "LOSS" else 0,
                  rank, rank))
        
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
            SELECT timestamp, my_deck, opponent_deck, result, my_rank
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
        conn.close()
        
        return row if row else (0, 0, 0, None, None)


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
