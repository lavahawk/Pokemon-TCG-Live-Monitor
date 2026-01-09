"""
Auto-Clicker Module for Pokemon TCG Live
Automatically clicks buttons when they appear on screen using template matching
"""

import cv2
import numpy as np
import mss
import pyautogui
import time
import os
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "button_templates")


class AutoClicker:
    """Handles automatic button clicking when buttons appear on screen"""
    
    def __init__(self, game_window):
        """
        Initialize AutoClicker
        
        Args:
            game_window: Dict with game window bounds {'left', 'top', 'width', 'height'}
        """
        self.game_window = game_window
        self.sct = mss.mss()
        self.templates = {}
        self.last_click_time = {}
        self.click_cooldown = 2.0  # Minimum seconds between clicks on same button
        
        # Create templates directory if it doesn't exist
        if not os.path.exists(TEMPLATES_DIR):
            os.makedirs(TEMPLATES_DIR)
            print(f"Created templates directory: {TEMPLATES_DIR}")
    
    def load_template(self, template_name, threshold=0.8):
        """
        Load a button template image for matching
        
        Args:
            template_name: Name of the template file (without extension)
            threshold: Match confidence threshold (0.0 to 1.0)
        
        Returns:
            True if template loaded successfully
        """
        template_path = os.path.join(TEMPLATES_DIR, f"{template_name}.png")
        
        if not os.path.exists(template_path):
            print(f"Warning: Template not found: {template_path}")
            print(f"To create a template:")
            print(f"1. Take a screenshot of the button")
            print(f"2. Crop just the button area")
            print(f"3. Save as: {template_path}")
            return False
        
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            print(f"Error: Could not load template: {template_path}")
            return False
        
        self.templates[template_name] = {
            'image': template,
            'threshold': threshold,
            'width': template.shape[1],
            'height': template.shape[0]
        }
        
        print(f"✓ Loaded template: {template_name} ({template.shape[1]}x{template.shape[0]})")
        return True
    
    def find_button(self, template_name, region=None):
        """
        Find a button on screen using template matching
        
        Args:
            template_name: Name of the loaded template
            region: Optional region to search {'left', 'top', 'width', 'height'}
                   If None, searches entire game window
        
        Returns:
            (x, y) center coordinates if found, None otherwise
        """
        if template_name not in self.templates:
            return None
        
        template_data = self.templates[template_name]
        template = template_data['image']
        threshold = template_data['threshold']
        
        # Determine search region
        if region is None:
            region = self.game_window
        
        # Capture screen region
        monitor = {
            'left': region['left'],
            'top': region['top'],
            'width': region['width'],
            'height': region['height']
        }
        
        try:
            screenshot = self.sct.grab(monitor)
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            # Perform template matching
            result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            # Check if match is good enough
            if max_val >= threshold:
                # Calculate center of button
                center_x = region['left'] + max_loc[0] + template_data['width'] // 2
                center_y = region['top'] + max_loc[1] + template_data['height'] // 2
                
                return (center_x, center_y)
            
        except Exception as e:
            print(f"Error finding button {template_name}: {e}")
        
        return None
    
    def click_button(self, template_name, region=None, force=False):
        """
        Find and click a button if it's visible
        
        Args:
            template_name: Name of the loaded template
            region: Optional region to search
            force: If True, ignore click cooldown
        
        Returns:
            True if button was found and clicked
        """
        # Check cooldown
        if not force:
            last_click = self.last_click_time.get(template_name, 0)
            if time.time() - last_click < self.click_cooldown:
                return False
        
        # Find button
        coords = self.find_button(template_name, region)
        
        if coords:
            x, y = coords
            
            # Move and click
            pyautogui.click(x, y)
            self.last_click_time[template_name] = time.time()
            
            print(f"✓ Clicked {template_name} at ({x}, {y})")
            return True
        
        return False
    
    def watch_and_click(self, buttons, region=None, interval=0.5, duration=30):
        """
        Continuously watch for buttons and click them when they appear
        
        Args:
            buttons: List of button template names to watch for
            region: Optional region to watch
            interval: Time between checks in seconds
            duration: Maximum time to watch in seconds (0 = infinite)
        
        Returns:
            List of buttons that were clicked
        """
        start_time = time.time()
        clicked_buttons = []
        
        print(f"Watching for buttons: {buttons}")
        
        while True:
            # Check duration
            if duration > 0 and time.time() - start_time > duration:
                print(f"Watch timeout after {duration}s")
                break
            
            # Check each button
            for button_name in buttons:
                if self.click_button(button_name, region):
                    clicked_buttons.append(button_name)
            
            # Wait before next check
            time.sleep(interval)
        
        return clicked_buttons
    
    def create_template_from_screen(self, template_name, x, y, width, height):
        """
        Capture a region of the screen and save as a template
        
        Args:
            template_name: Name to save template as
            x, y: Top-left corner of region (screen coordinates)
            width, height: Size of region
        """
        monitor = {
            'left': x,
            'top': y,
            'width': width,
            'height': height
        }
        
        try:
            screenshot = self.sct.grab(monitor)
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            template_path = os.path.join(TEMPLATES_DIR, f"{template_name}.png")
            cv2.imwrite(template_path, img)
            
            print(f"✓ Template saved: {template_path}")
            print(f"  Region: ({x}, {y}) {width}x{height}")
            
            # Automatically load it
            self.load_template(template_name)
            
        except Exception as e:
            print(f"Error creating template: {e}")


# Example usage
if __name__ == "__main__":
    from RankDetector import RankDetector
    
    # Find game window
    detector = RankDetector()
    game_window = detector.find_game_window()
    
    if not game_window:
        print("Error: Pokemon TCG Live window not found!")
        print("Please start the game first.")
        exit(1)
    
    print(f"Found game window: {game_window['width']}x{game_window['height']}")
    
    # Create AutoClicker
    clicker = AutoClicker(game_window)
    
    # Example: Load and watch for buttons
    # First, you need to create templates by capturing button images
    print("\n" + "="*50)
    print("AutoClicker Setup:")
    print("="*50)
    print("1. Take screenshots of the buttons you want to click")
    print("2. Crop just the button area (as small as possible)")
    print(f"3. Save them in: {TEMPLATES_DIR}")
    print("   Example names: continue.png, ok.png, claim.png")
    print("\nOr use create_template_from_screen() to capture from screen")
    print("="*50)
    
    # Example: If templates exist, watch for them
    example_buttons = ["continue", "ok"]
    
    for button in example_buttons:
        clicker.load_template(button, threshold=0.8)
    
    # Watch for 10 seconds
    # clicker.watch_and_click(example_buttons, duration=10)
