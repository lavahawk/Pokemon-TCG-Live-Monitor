"""
View Current Stats
Quick script to view your max rank and other stats
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_RANK_FILE = os.path.join(BASE_DIR, ".max_rank")
RANK_FILE = os.path.join(BASE_DIR, ".last_rank")
DECK_FILE = os.path.join(BASE_DIR, ".last_deck")

def main():
    print("\n" + "="*50)
    print("🏆 POKEMON TCG LIVE STATS")
    print("="*50 + "\n")
    
    # Max rank
    if os.path.exists(MAX_RANK_FILE):
        with open(MAX_RANK_FILE, "r") as f:
            max_rank = f.read().strip()
        print(f"🎯 Max Rank Achieved: {max_rank}")
    else:
        print("📊 Max Rank: Not yet recorded")
    
    # Current rank
    if os.path.exists(RANK_FILE):
        with open(RANK_FILE, "r") as f:
            current_rank = f.read().strip()
        print(f"📈 Last Detected Rank: {current_rank}")
    else:
        print("📈 Last Detected Rank: None")
    
    # Last deck
    if os.path.exists(DECK_FILE):
        with open(DECK_FILE, "r") as f:
            deck = f.read().strip()
        print(f"🃏 Last Deck: {deck}")
    else:
        print("🃏 Last Deck: None")
    
    print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    main()
    input("Press Enter to exit...")
