"""
Test Validation Methods - Test screen validation to prevent false positives
"""

from RankDetector import RankDetector
import time

def print_header(title):
    print("\n" + "="*60)
    print(title)
    print("="*60 + "\n")

def test_menu_text_validation():
    """Test menu text detection (looking for PLAY, SHOP buttons)"""
    print_header("TEST 1: Menu Text Validation")
    print("This method looks for specific text like 'PLAY' or 'SHOP'")
    print("\nYou need to configure a 'menu_text' region first!")
    print("Run SetupRegions.py and create a region containing the PLAY button")
    print("\nPress Enter when ready (or Ctrl+C to skip)...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nSkipped.")
        return
    
    detector = RankDetector()
    result = detector.is_on_main_menu(validation_method="text", debug=True)
    
    print(f"\n✓ Menu detected: {result}")
    
    if result:
        rank = detector.extract_rank_safe(validate_screen=True, debug=True)
        print(f"\n✓ Rank detected: {rank}")
    else:
        print("\n✗ Not on main menu - rank detection blocked (this is good!)")

def test_template_validation():
    """Test template matching validation"""
    print_header("TEST 2: Template Matching Validation")
    print("This method compares against a saved screenshot of a UI element")
    print("\nYou need to create a template first!")
    print("Run CaptureTemplate.py to capture a unique UI element")
    print("\nPress Enter when ready (or Ctrl+C to skip)...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nSkipped.")
        return
    
    print("\nWhich template did you create?")
    print("Enter the filename (e.g., main_menu_indicator.png):")
    template_name = input("> ").strip()
    
    if not template_name:
        print("Skipped.")
        return
    
    detector = RankDetector()
    result = detector.validate_screen_by_template(
        region=None,  # Will use full screen
        template_path=f"templates/{template_name}",
        threshold=0.8,
        debug=True
    )
    
    print(f"\n✓ Template match: {result}")

def test_pixel_validation():
    """Test pixel color validation"""
    print_header("TEST 3: Pixel Color Validation")
    print("This method checks if specific pixels have expected colors")
    print("\nThis is advanced - usually text or template validation is enough.")
    print("\nPress Enter to run test (or Ctrl+C to skip)...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nSkipped.")
        return
    
    print("\nNote: This test will show you HOW to use pixel validation,")
    print("but you'll need to configure the expected colors yourself.")
    
    # Example (you need to customize this)
    example_config = {
        "name": "pixel_check",
        "relative": True,
        "offset_x": 100,
        "offset_y": 100,
        "width": 10,
        "height": 10,
        "expected_colors": [
            {"x": 5, "y": 5, "rgb": [255, 255, 255], "tolerance": 20}
        ]
    }
    
    print("\nExample configuration:")
    print(example_config)
    print("\nYou would add this to screen_regions.json")

def test_auto_validation():
    """Test automatic validation (combines multiple methods)"""
    print_header("TEST 4: Auto Validation (Recommended)")
    print("This combines multiple validation methods for best accuracy")
    print("\nMake sure you have:")
    print("1. 'menu_text' region configured (containing PLAY button)")
    print("2. Template image saved (optional but recommended)")
    print("\nPress Enter when ready (or Ctrl+C to skip)...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nSkipped.")
        return
    
    detector = RankDetector()
    
    print("\n--- Testing on MAIN MENU screen ---")
    print("Make sure the game is on the main menu, then press Enter...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nSkipped.")
        return
    
    result = detector.extract_rank_safe(validate_screen=True, debug=True)
    print(f"\n✓ Rank detected on main menu: {result}")
    
    print("\n--- Testing on DIFFERENT screen ---")
    print("Switch to a DIFFERENT screen (deck builder, collection, battle, etc.)")
    print("then press Enter...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nSkipped.")
        return
    
    result = detector.extract_rank_safe(validate_screen=True, debug=True)
    
    if result is None:
        print("\n✓ SUCCESS! Validation correctly blocked detection on wrong screen!")
    else:
        print(f"\n✗ WARNING: Detected '{result}' on wrong screen (false positive)")
        print("   You may need to adjust validation settings")

def main():
    print("\n" + "="*60)
    print("VALIDATION TESTING TOOL")
    print("="*60)
    print("\nThis tool helps you test screen validation to prevent false positives.")
    print("\nWhen rank detection is validated:")
    print("✓ Numbers on main menu → DETECT")
    print("✓ Numbers after battle → DETECT")
    print("✗ Numbers in deck builder → IGNORE")
    print("✗ Numbers in collection → IGNORE")
    print("✗ Battle damage numbers → IGNORE")
    
    while True:
        print("\n" + "-"*60)
        print("Choose a test:")
        print("-"*60)
        print("1. Test Menu Text Validation (recommended for beginners)")
        print("2. Test Template Matching (most accurate)")
        print("3. Test Pixel Color Validation (advanced)")
        print("4. Test Auto Validation (combines all methods)")
        print("0. Exit")
        print("-"*60)
        
        choice = input("\nEnter choice (0-4): ").strip()
        
        if choice == "0":
            print("\nExiting...")
            break
        elif choice == "1":
            test_menu_text_validation()
        elif choice == "2":
            test_template_validation()
        elif choice == "3":
            test_pixel_validation()
        elif choice == "4":
            test_auto_validation()
        else:
            print("\nInvalid choice. Try again.")
        
        print("\n" + "="*60)
        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting...")
