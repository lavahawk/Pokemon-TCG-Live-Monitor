"""
Example Integration: Add OCR Rank and Deck Detection to Battle Log Workflow

This shows how to integrate rank and deck name detection into your existing workflow.
The plan:
1. Battle log detected → save to file
2. Run AI parser to identify opponent deck and W/L
3. Use OCR to detect YOUR actual deck name from screen (more accurate than AI)
4. Use OCR to detect your current rank
5. Save all data to Excel

This replaces AI-guessed deck with OCR-detected deck for better accuracy!
"""

import os
import time
from RankDetector import RankDetector

# Initialize detector once
detector = RankDetector()


def detect_rank_after_battle():
    """
    Detect rank after a battle is logged
    Call this after saving battle log but before running AI parser
    """
    print("\n" + "="*50)
    print("Detecting rank from screen...")
    print("="*50)
    
    # Give game time to show post-battle screen
    time.sleep(2)
    
    # Try to detect rank (with retries for reliability)
    rank = detector.get_rank_with_retry(max_attempts=3, delay=0.5)
    
    if rank:
        print(f"✓ Current Rank: {rank}")
        return rank
    else:
        print("⚠ Could not detect rank (game might not be on main menu)")
        return None


def detect_my_deck_name():
    """
    Detect your actual deck name from screen
    More accurate than AI guessing from battle log
    
    Call this when you're on deck selection or post-battle screen
    where your deck name is visible
    """
    print("\n" + "="*50)
    print("Detecting your deck name from screen...")
    print("="*50)
    
    # Check if deck name region is configured
    if "my_deck_name" not in detector.regions:
        print("⚠ Deck name region not configured!")
        print("  Run SetupRegions.py and define 'my_deck_name' region")
        return None
    
    # Try to extract deck name
    deck_name = detector.extract_text("my_deck_name", debug=False)
    
    if deck_name:
        # Clean up the text
        deck_name = deck_name.strip()
        print(f"✓ Your Deck: {deck_name}")
        return deck_name
    else:
        print("⚠ Could not detect deck name")
        return None


def save_battle_data_with_ocr(battle_log_path, ai_results):
    """
    Enhanced version of saving battle data
    Combines AI results with OCR detection
    
    Args:
        battle_log_path: Path to saved battle log file
        ai_results: Dictionary from AI parser with:
                   {'My_deck': ..., 'OpponentsDeck': ..., 'Win_or_Loss': ..., 'Confidence': ...}
    
    Returns:
        Enhanced results dictionary with OCR data
    """
    print("\n" + "="*50)
    print("Enhancing battle data with OCR...")
    print("="*50)
    
    # Start with AI results
    enhanced_data = ai_results.copy()
    
    # Detect rank
    rank = detect_rank_after_battle()
    if rank:
        enhanced_data['Rank'] = rank
    
    # Detect actual deck name (more accurate than AI)
    my_deck = detect_my_deck_name()
    if my_deck:
        print(f"\n📝 Replacing AI deck guess with OCR detection:")
        print(f"   AI guessed: {ai_results.get('My_deck', 'Unknown')}")
        print(f"   OCR detected: {my_deck}")
        enhanced_data['My_deck'] = my_deck  # Override AI guess
        enhanced_data['Deck_Source'] = 'OCR'  # Track where deck came from
    else:
        print(f"\n📝 Using AI deck detection (OCR not available)")
        enhanced_data['Deck_Source'] = 'AI'
    
    # Display final results
    print("\n" + "="*50)
    print("BATTLE RESULTS:")
    print("="*50)
    print(f"Your Deck:      {enhanced_data.get('My_deck', 'Unknown')} ({enhanced_data.get('Deck_Source', 'Unknown')})")
    print(f"Opponent Deck:  {enhanced_data.get('OpponentsDeck', 'Unknown')}")
    print(f"Result:         {enhanced_data.get('Win_or_Loss', 'Unknown')}")
    print(f"AI Confidence:  {enhanced_data.get('Confidence', 0)}%")
    print(f"Current Rank:   {enhanced_data.get('Rank', 'N/A')}")
    print("="*50)
    
    return enhanced_data


# Example usage in your TCGLiveMonitor workflow:
"""
def monitor_clipboard():
    previous_clipboard = ""
    while True:
        if is_pokemon_tcg_live_running():
            clipboard_content = pyperclip.paste()
            time.sleep(2)
            
            if clipboard_content != previous_clipboard and is_battle_log(clipboard_content):
                # 1. Save battle log
                save_battle_log(clipboard_content)
                play_sound()
                
                # 2. Run AI parser to get initial analysis
                ai_results = run_ai_parser()  # Returns dict with AI analysis
                
                # 3. NEW: Enhance with OCR detection
                from IntegrateOCR_Example import save_battle_data_with_ocr
                final_results = save_battle_data_with_ocr(
                    battle_log_path=latest_log_file,
                    ai_results=ai_results
                )
                
                # 4. Save enhanced results to Excel
                save_to_excel(final_results)
                
                previous_clipboard = clipboard_content
        else:
            wait_for_game_startup()
"""


def test_integration():
    """Test the OCR integration"""
    print("\n" + "="*50)
    print("TESTING OCR INTEGRATION")
    print("="*50)
    print("\nMake sure:")
    print("1. Pokemon TCG Live is running")
    print("2. You're on a screen where rank is visible")
    print("3. Regions are configured (run SetupRegions.py)")
    print("\nPress Enter to test...")
    input()
    
    # Simulate AI results
    mock_ai_results = {
        'My_deck': 'Charizard ex (AI guess)',
        'OpponentsDeck': 'Pikachu ex',
        'Win_or_Loss': 'Win',
        'Confidence': 85
    }
    
    # Test OCR enhancement
    enhanced = save_battle_data_with_ocr(
        battle_log_path="test_log.txt",
        ai_results=mock_ai_results
    )
    
    print("\n✓ Integration test complete!")
    print("\nNext steps:")
    print("1. Configure 'my_deck_name' region in SetupRegions.py")
    print("2. Integrate this code into BackgroundRun/TCGLiveMonitor.py")
    print("3. Update AIParseBattleLog.py to use OCR deck instead of AI deck")


if __name__ == "__main__":
    test_integration()
