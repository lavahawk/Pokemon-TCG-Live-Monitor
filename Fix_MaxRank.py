"""
Fix Max Rank - Corrects the max rank in the database
"""
import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tcg_battles.db")

def view_rank_history():
    """Show all rank history entries"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, timestamp, rank, deck_name FROM rank_history ORDER BY timestamp DESC LIMIT 20")
    rows = cursor.fetchall()
    
    print("\n" + "="*80)
    print("RECENT RANK HISTORY (Last 20 entries)")
    print("="*80)
    print(f"{'ID':<5} {'Timestamp':<20} {'Rank':<10} {'Deck':<30}")
    print("-"*80)
    
    for row in rows:
        id_val, timestamp, rank, deck = row
        deck_display = (deck[:27] + "...") if deck and len(deck) > 30 else (deck or "N/A")
        print(f"{id_val:<5} {timestamp:<20} {rank:<10} {deck_display:<30}")
    
    conn.close()
    print("="*80 + "\n")

def delete_bad_rank_entry(entry_id):
    """Delete a specific rank history entry by ID"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM rank_history WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    
    print(f"✓ Deleted rank history entry ID: {entry_id}")

def set_correct_max_rank(correct_rank):
    """Manually set the correct max rank in .max_rank file"""
    max_rank_file = os.path.join(BASE_DIR, ".max_rank")
    with open(max_rank_file, "w") as f:
        f.write(str(correct_rank))
    print(f"✓ Set .max_rank file to: {correct_rank}")

def main():
    print("\n=== Fix Max Rank Tool ===\n")
    
    # Show current rank history
    view_rank_history()
    
    print("Options:")
    print("1. Delete a bad rank entry (by ID)")
    print("2. Set correct max rank manually")
    print("3. Exit")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        entry_id = input("Enter the ID of the entry to delete: ").strip()
        try:
            delete_bad_rank_entry(int(entry_id))
            view_rank_history()  # Show updated list
        except ValueError:
            print("Error: Invalid ID")
    
    elif choice == "2":
        correct_rank = input("Enter your correct max rank: ").strip()
        try:
            set_correct_max_rank(int(correct_rank))
        except ValueError:
            print("Error: Invalid rank number")
    
    elif choice == "3":
        print("Exiting...")
    
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main()
