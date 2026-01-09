"""
Button Template Capture Tool
Interactive tool to capture button templates from the game screen
"""

import cv2
import numpy as np
import mss
from RankDetector import RankDetector
from AutoClicker import AutoClicker
import time

def capture_button_template():
    """Interactive tool to capture button templates"""
    
    # Find game window
    detector = RankDetector()
    game_window = detector.find_game_window()
    
    if not game_window:
        print("Error: Pokemon TCG Live window not found!")
        print("Please start the game and navigate to the screen with the button you want to capture.")
        return
    
    print("\n" + "="*60)
    print("BUTTON TEMPLATE CAPTURE TOOL")
    print("="*60)
    print(f"Game Window: {game_window['width']}x{game_window['height']}")
    print()
    print("Instructions:")
    print("1. Navigate to the screen where the button appears")
    print("2. Enter the button coordinates and size")
    print("3. Template will be saved for auto-clicking")
    print()
    print("TIP: Use a screenshot tool to measure button position and size")
    print("="*60)
    print()
    
    # Get button name
    button_name = input("Enter button name (e.g., 'continue', 'ok', 'claim'): ").strip()
    
    if not button_name:
        print("Error: Button name required")
        return
    
    # Get coordinates (relative to game window)
    print("\nEnter coordinates RELATIVE to game window top-left corner:")
    print("(Use a screenshot tool to measure from the game window edge)")
    
    try:
        rel_x = int(input("  X position (pixels from left edge): "))
        rel_y = int(input("  Y position (pixels from top edge): "))
        width = int(input("  Button width (pixels): "))
        height = int(input("  Button height (pixels): "))
    except ValueError:
        print("Error: Invalid coordinates")
        return
    
    # Convert to screen coordinates
    screen_x = game_window['left'] + rel_x
    screen_y = game_window['top'] + rel_y
    
    # Confirm
    print(f"\nCapture region:")
    print(f"  Relative: ({rel_x}, {rel_y}) {width}x{height}")
    print(f"  Screen:   ({screen_x}, {screen_y}) {width}x{height}")
    
    confirm = input("\nCapture template? (y/n): ").strip().lower()
    
    if confirm == 'y':
        # Create AutoClicker and capture
        clicker = AutoClicker(game_window)
        clicker.create_template_from_screen(button_name, screen_x, screen_y, width, height)
        
        print(f"\n✓ Template '{button_name}' created successfully!")
        print(f"\nYou can now use this in AutoClicker:")
        print(f"  clicker.load_template('{button_name}')")
        print(f"  clicker.click_button('{button_name}')")
    else:
        print("Cancelled")


def test_button_detection():
    """Test if a button template can be detected on screen"""
    
    # Find game window
    detector = RankDetector()
    game_window = detector.find_game_window()
    
    if not game_window:
        print("Error: Pokemon TCG Live window not found!")
        return
    
    print("\n" + "="*60)
    print("BUTTON DETECTION TEST")
    print("="*60)
    
    # Create AutoClicker
    clicker = AutoClicker(game_window)
    
    # Get button name
    button_name = input("Enter button template name to test: ").strip()
    
    if not button_name:
        print("Error: Button name required")
        return
    
    # Load template
    if not clicker.load_template(button_name, threshold=0.8):
        return
    
    print(f"\nSearching for '{button_name}' button...")
    print("(Make sure the button is visible on screen)")
    
    # Try to find it
    coords = clicker.find_button(button_name)
    
    if coords:
        print(f"✓ Button found at: {coords}")
        
        test_click = input("\nTest click? (y/n): ").strip().lower()
        if test_click == 'y':
            clicker.click_button(button_name, force=True)
    else:
        print("✗ Button not found")
        print("\nTroubleshooting:")
        print("1. Make sure the button is visible on screen")
        print("2. Check that the template image matches the current button appearance")
        print("3. Try lowering the threshold (currently 0.8)")


def watch_for_buttons():
    """Watch for multiple buttons and click them"""
    
    # Find game window
    detector = RankDetector()
    game_window = detector.find_game_window()
    
    if not game_window:
        print("Error: Pokemon TCG Live window not found!")
        return
    
    print("\n" + "="*60)
    print("BUTTON AUTO-CLICKER")
    print("="*60)
    
    # Create AutoClicker
    clicker = AutoClicker(game_window)
    
    # Get button names
    print("Enter button names to watch for (comma-separated):")
    print("Example: continue,ok,claim")
    buttons_input = input("> ").strip()
    
    if not buttons_input:
        print("Error: No buttons specified")
        return
    
    button_names = [b.strip() for b in buttons_input.split(',')]
    
    # Load templates
    print("\nLoading templates...")
    loaded_buttons = []
    for button in button_names:
        if clicker.load_template(button, threshold=0.8):
            loaded_buttons.append(button)
    
    if not loaded_buttons:
        print("Error: No valid templates loaded")
        return
    
    # Get duration
    try:
        duration = int(input("\nWatch duration in seconds (0 = until stopped): "))
    except ValueError:
        duration = 30
    
    # Start watching
    print(f"\n{'='*60}")
    print(f"Watching for buttons: {', '.join(loaded_buttons)}")
    print(f"Duration: {duration}s" if duration > 0 else "Duration: Until stopped (Ctrl+C to stop)")
    print(f"{'='*60}\n")
    
    try:
        clicker.watch_and_click(loaded_buttons, duration=duration, interval=0.5)
    except KeyboardInterrupt:
        print("\n\nStopped by user")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("POKEMON TCG LIVE - BUTTON AUTO-CLICKER SETUP")
    print("="*60)
    print()
    print("Options:")
    print("1. Capture new button template")
    print("2. Test button detection")
    print("3. Watch and auto-click buttons")
    print("4. Exit")
    print()
    
    choice = input("Select option (1-4): ").strip()
    
    if choice == '1':
        capture_button_template()
    elif choice == '2':
        test_button_detection()
    elif choice == '3':
        watch_for_buttons()
    elif choice == '4':
        print("Goodbye!")
    else:
        print("Invalid choice")
