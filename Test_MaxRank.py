"""
Test Max Rank Tracking
Tests the max rank storage and update functionality
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_RANK_FILE = os.path.join(BASE_DIR, ".max_rank")

def load_max_rank():
    """Load the highest rank achieved."""
    if os.path.exists(MAX_RANK_FILE):
        with open(MAX_RANK_FILE, "r") as file:
            try:
                rank_str = file.read().strip()
                return int(rank_str) if rank_str else None
            except ValueError:
                return None
    return None

def save_max_rank(rank):
    """Save the highest rank achieved."""
    with open(MAX_RANK_FILE, "w") as file:
        file.write(str(rank))
    print(f"🏆 Saved max rank: {rank}")

def update_max_rank(current_rank):
    """Update max rank if current rank is higher."""
    if current_rank is None:
        return False
    
    max_rank = load_max_rank()
    
    if max_rank is None:
        print(f"📝 First rank recorded: {current_rank}")
        save_max_rank(current_rank)
        return True
    elif current_rank > max_rank:
        print(f"🎉 NEW RECORD! {current_rank} (previous: {max_rank})")
        save_max_rank(current_rank)
        return True
    else:
        print(f"📊 Current: {current_rank} | Max: {max_rank}")
        return False

def main():
    print("\n" + "="*50)
    print("MAX RANK TRACKING TEST")
    print("="*50)
    
    # Test scenarios
    test_ranks = [50, 65, 80, 75, 90, 85, 92, 88]
    
    print("\nTesting with ranks:", test_ranks)
    print()
    
    for rank in test_ranks:
        print(f"\n--- Testing rank: {rank} ---")
        update_max_rank(rank)
    
    print("\n" + "="*50)
    final_max = load_max_rank()
    print(f"FINAL MAX RANK: {final_max}")
    print("="*50)
    
    # Show current max rank file location
    print(f"\n📁 Max rank stored in: {MAX_RANK_FILE}")
    
    # Ask if user wants to reset
    response = input("\nReset max rank? (y/n): ")
    if response.lower() == 'y':
        if os.path.exists(MAX_RANK_FILE):
            os.remove(MAX_RANK_FILE)
            print("✓ Max rank reset!")
        else:
            print("No max rank file found.")

if __name__ == "__main__":
    main()
