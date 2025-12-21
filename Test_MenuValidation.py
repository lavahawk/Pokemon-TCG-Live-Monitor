"""
Quick Test - Menu Text Validation
Tests if rank detection only works on main menu
"""

from RankDetector import RankDetector
import time

def main():
    print("\n" + "="*60)
    print("TESTING MENU TEXT VALIDATION")
    print("="*60)
    
    detector = RankDetector()
    
    # Test 1: On main menu
    print("\n--- TEST 1: Main Menu Detection ---")
    print("Make sure Pokemon TCG Live is on the MAIN MENU")
    print("Press Enter when ready...")
    input()
    
    print("\nChecking if we're on main menu...")
    is_menu = detector.is_on_main_menu(validation_method="text", debug=True)
    
    if is_menu:
        print("\n✓ SUCCESS! Main menu detected!")
        print("\nNow trying to detect rank...")
        rank = detector.extract_rank_safe(validate_screen=True, debug=True)
        if rank:
            print(f"\n✓ Rank detected: {rank}")
        else:
            print("\n(No rank number visible - that's OK)")
    else:
        print("\n✗ FAILED! Main menu not detected")
        print("Check if the menu_text region is correctly positioned")
        return
    
    # Test 2: On different screen
    print("\n\n--- TEST 2: False Positive Prevention ---")
    print("Now switch to a DIFFERENT screen:")
    print("- Deck Builder (has lots of card numbers)")
    print("- Collection (has card counts)")
    print("- Any other screen with numbers")
    print("\nPress Enter when you've switched screens...")
    input()
    
    print("\nChecking if we're on main menu...")
    is_menu = detector.is_on_main_menu(validation_method="text", debug=True)
    
    if not is_menu:
        print("\n✓ SUCCESS! Correctly detected we're NOT on main menu!")
        print("\nTrying rank detection (should be blocked)...")
        rank = detector.extract_rank_safe(validate_screen=True, debug=True)
        if rank is None:
            print("\n✓ PERFECT! Rank detection was blocked (prevented false positive)")
        else:
            print(f"\n✗ WARNING: Still detected '{rank}' (shouldn't happen)")
    else:
        print("\n✗ PROBLEM: Still thinks we're on main menu")
        print("The menu_text region may be seeing text that appears on multiple screens")
        print("Try using a template instead, or make the region more specific")
    
    print("\n" + "="*60)
    print("VALIDATION TEST COMPLETE")
    print("="*60)
    print("\nIf both tests passed:")
    print("✓ Detection works on main menu")
    print("✓ Detection is blocked on other screens")
    print("\nYou're ready to integrate this into the battle log workflow!")
    print("="*60 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest cancelled.")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
