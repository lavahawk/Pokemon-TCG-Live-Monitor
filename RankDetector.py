"""
Rank Detector Module - OCR-based screen scanning for Pokemon TCG Live
Detects rank numbers from the main menu using region-based OCR
Works at any resolution using WINDOW-RELATIVE positioning
Automatically finds the game window regardless of position
"""

import cv2
import numpy as np
import mss
import pytesseract
import json
import os
import win32gui
import win32process
import psutil
from PIL import Image

# Get the script's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REGIONS_CONFIG = os.path.join(BASE_DIR, "screen_regions.json")

# Configure Tesseract path
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


class RankDetector:
    """Handles OCR-based rank detection from screen regions"""
    
    def __init__(self):
        self.regions = self.load_regions()
        self.sct = mss.mss()
        self.game_window = None
        self.screen_validators = {}  # Cache for screen validation templates
    
    def load_regions(self):
        """Load saved screen regions from config file"""
        if os.path.exists(REGIONS_CONFIG):
            with open(REGIONS_CONFIG, 'r') as f:
                return json.load(f)
        return {}
    
    def save_regions(self, regions):
        """Save screen regions to config file"""
        with open(REGIONS_CONFIG, 'w') as f:
            json.dump(regions, f, indent=4)
        self.regions = regions
    
    def find_game_window(self):
        """
        Find the Pokemon TCG Live game window
        
        Returns:
            dict with window bounds: {'left': x, 'top': y, 'width': w, 'height': h}
            or None if window not found
        """
        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                window_title = win32gui.GetWindowText(hwnd)
                # Check for Pokemon TCG Live window
                if "Pokémon TCG Live" in window_title or "Pokemon TCG Live" in window_title:
                    # Get window rectangle
                    rect = win32gui.GetWindowRect(hwnd)
                    left, top, right, bottom = rect
                    
                    # Store window info
                    windows.append({
                        'hwnd': hwnd,
                        'title': window_title,
                        'left': left,
                        'top': top,
                        'width': right - left,
                        'height': bottom - top
                    })
            return True
        
        windows = []
        win32gui.EnumWindows(callback, windows)
        
        if windows:
            # Return the first matching window
            self.game_window = windows[0]
            return self.game_window
        
        # Alternative: Find by process name
        for proc in psutil.process_iter(['name', 'pid']):
            if proc.info['name'] == "Pokemon TCG Live.exe":
                # Try to find window by process ID
                def find_by_pid(hwnd, result):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid == proc.info['pid'] and win32gui.IsWindowVisible(hwnd):
                        rect = win32gui.GetWindowRect(hwnd)
                        left, top, right, bottom = rect
                        result.append({
                            'hwnd': hwnd,
                            'title': win32gui.GetWindowText(hwnd),
                            'left': left,
                            'top': top,
                            'width': right - left,
                            'height': bottom - top
                        })
                    return True
                
                result = []
                win32gui.EnumWindows(find_by_pid, result)
                if result:
                    self.game_window = result[0]
                    return self.game_window
        
        return None
    
    def get_absolute_region(self, region_name):
        """
        Get absolute screen coordinates for a region
        Automatically adjusts for window position AND scales with window size
        
        Args:
            region_name: Name of the region
            
        Returns:
            dict with absolute coordinates or None
        """
        if region_name not in self.regions:
            print(f"Region '{region_name}' not found in config.")
            return None
        
        region = self.regions[region_name]
        
        # Check if region uses relative coordinates (has 'relative' flag)
        if region.get('relative', False):
            # Find game window
            window = self.find_game_window()
            if not window:
                print("Game window not found! Is Pokemon TCG Live running?")
                return None
            
            # Check if region uses percentage-based positioning (NEW in v2.0)
            if 'percent_x' in region and 'percent_y' in region:
                # Scale position and size based on window dimensions
                offset_x = int(window['width'] * region['percent_x'])
                offset_y = int(window['height'] * region['percent_y'])
                width = int(window['width'] * region['percent_width'])
                height = int(window['height'] * region['percent_height'])
                
                return {
                    'left': window['left'] + offset_x,
                    'top': window['top'] + offset_y,
                    'width': width,
                    'height': height
                }
            else:
                # Old pixel-based offsets (backwards compatible but won't scale)
                return {
                    'left': window['left'] + region['offset_x'],
                    'top': window['top'] + region['offset_y'],
                    'width': region['width'],
                    'height': region['height']
                }
        else:
            # Old format: absolute coordinates (backwards compatible)
            return {
                'left': region['left'],
                'top': region['top'],
                'width': region['width'],
                'height': region['height']
            }
    
    def capture_region(self, region_name):
        """
        Capture a specific screen region
        Automatically finds game window and adjusts coordinates
        
        Args:
            region_name: Name of the region defined in config
            
        Returns:
            PIL Image of the captured region or None if region not found
        """
        # Get absolute coordinates (handles both relative and absolute regions)
        abs_region = self.get_absolute_region(region_name)
        if not abs_region:
            return None
        
        # Validate region bounds
        if abs_region["width"] <= 0 or abs_region["height"] <= 0:
            return None
        
        if abs_region["left"] < 0 or abs_region["top"] < 0:
            return None
        
        # Capture the screen region
        monitor = {
            "top": abs_region["top"],
            "left": abs_region["left"],
            "width": abs_region["width"],
            "height": abs_region["height"]
        }
        
        try:
            screenshot = self.sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return img
        except Exception as e:
            return None
    
    def check_pixel_colors(self, region_name, expected_colors):
        """
        Check if specific pixels in a region match expected colors
        Used for screen validation
        
        Args:
            region_name: Region to check
            expected_colors: List of tuples: [(x_offset, y_offset, (r, g, b), tolerance), ...]
                x_offset, y_offset: Position within the region
                (r, g, b): Expected RGB color
                tolerance: Allowed color difference (0-255)
        
        Returns:
            Boolean - True if all pixels match within tolerance
        """
        img = self.capture_region(region_name)
        if not img:
            return False
        
        img_array = np.array(img)
        
        for x, y, expected_rgb, tolerance in expected_colors:
            if x >= img_array.shape[1] or y >= img_array.shape[0]:
                return False
            
            actual_rgb = img_array[y, x][:3]  # Get RGB, ignore alpha if present
            
            # Calculate color difference
            diff = np.abs(actual_rgb.astype(int) - np.array(expected_rgb).astype(int))
            
            if np.any(diff > tolerance):
                return False
        
        return True
    
    def validate_screen_by_template(self, region_name, template_path, threshold=0.8):
        """
        Check if a template image exists in the captured region
        Used to detect specific screens (main menu, post-battle, etc.)
        
        Args:
            region_name: Region to search in
            template_path: Path to template image (small screenshot of unique UI element)
            threshold: Matching confidence (0.0-1.0), higher = stricter
        
        Returns:
            Boolean - True if template found
        """
        if not os.path.exists(template_path):
            print(f"Template not found: {template_path}")
            return False
        
        # Capture region
        img = self.capture_region(region_name)
        if not img:
            return False
        
        try:
            # Convert to OpenCV format
            img_array = np.array(img)
            if img_array.size == 0:
                return False
            
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        except Exception:
            return False
        
        # Load template
        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            return False
        
        # Template matching
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        return max_val >= threshold
    
    def validate_screen_by_text(self, region_name, expected_texts, partial_match=True):
        """
        Check if specific text appears in a region
        Used to confirm you're on the right screen
        
        Args:
            region_name: Region to check
            expected_texts: List of text strings to look for (e.g., ["PLAY", "SHOP"])
            partial_match: If True, checks if any expected text is in captured text
        
        Returns:
            Boolean - True if expected text found
        """
        img = self.capture_region(region_name)
        if not img:
            return False
        
        # Preprocess for OCR
        processed_img = self.preprocess_for_ocr(img, for_numbers=False)
        
        # Perform OCR
        text = pytesseract.image_to_string(processed_img).upper()
        
        # Check for expected text
        for expected in expected_texts:
            expected_upper = expected.upper()
            if partial_match:
                if expected_upper in text:
                    return True
            else:
                if expected_upper == text.strip():
                    return True
        
        return False
    
    def is_on_main_menu(self, validation_method="auto", debug=False):
        """
        Detect if the game is on the main menu screen
        Requires rank, deck name, AND menu text to all be present (v2.0)
        
        Args:
            validation_method: "auto", "strict", "text", "pixel", or "any"
                - "auto"/"strict": Requires all three elements (rank + deck + menu text)
                - "text": Look for menu text only
                - "pixel": Check pixel colors only
                - "any": Accept any validation (less strict)
            debug: Save debug images
        
        Returns:
            Boolean - True if on main menu
        """
        validations = []
        
        # Method 1: Check for menu text (if menu_text region defined)
        menu_found = False
        if "menu_text" in self.regions:
            menu_found = self.validate_screen_by_text(
                "menu_text", 
                ["PLAY", "SHOP", "CARDS", "BATTLE PASS", "DECK", "RANKED"]
            )
            validations.append(("menu_text", menu_found))
            if debug:
                print(f"  Menu text validation: {menu_found}")
        
        # Method 2: Check if rank is visible and valid
        rank = self.extract_rank(debug=debug)
        rank_valid = rank is not None and 0 < rank < 99999
        validations.append(("rank", rank_valid))
        if debug:
            print(f"  Rank validation: {rank_valid} (rank={rank})")
        
        # Method 3: Check if deck name is visible (NEW in v2.0)
        deck_found = False
        if "my_deck_name" in self.regions:
            # Use silent mode to avoid spam during waiting periods
            deck_text = self.extract_text("my_deck_name", debug=debug, silent=not debug)
            # Deck name should have at least 3 characters
            deck_found = deck_text is not None and len(deck_text.strip()) >= 3
            validations.append(("deck_name", deck_found))
            if debug:
                print(f"  Deck name validation: {deck_found} (deck={deck_text})")
        
        # Decide based on validation method
        if validation_method == "any":
            return any(result for _, result in validations)
        elif validation_method == "auto" or validation_method == "strict":
            # v2.0: Require ALL THREE elements to be present
            # This prevents false positives from other screens
            return rank_valid and menu_found and deck_found
        else:
            # Check specific method
            for method, result in validations:
                if method == validation_method:
                    return result
            return False
    
    def preprocess_for_ocr(self, image, for_numbers=True):
        """
        Preprocess image for better OCR accuracy
        
        Args:
            image: PIL Image
            for_numbers: If True, optimize for number recognition
            
        Returns:
            Preprocessed PIL Image
        """
        try:
            # Convert to OpenCV format
            img_array = np.array(image)
            if img_array.size == 0:
                return image
            
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # Convert to grayscale
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        except Exception:
            # If preprocessing fails, return original image
            return image
        
        # Apply thresholding to get black text on white background
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(thresh)
        
        # Resize for better OCR (make text larger)
        scale_factor = 2
        resized = cv2.resize(denoised, None, fx=scale_factor, fy=scale_factor, 
                            interpolation=cv2.INTER_CUBIC)
        
        # Convert back to PIL
        return Image.fromarray(resized)
    
    def extract_rank(self, region_name="rank", debug=False):
        """
        Extract rank number from screen
        
        Args:
            region_name: Name of the region to scan
            debug: If True, save debug images
            
        Returns:
            Integer rank number or None if not detected
        """
        # Capture the region
        img = self.capture_region(region_name)
        if img is None:
            return None
        
        # Preprocess for OCR
        processed_img = self.preprocess_for_ocr(img, for_numbers=True)
        
        # Save debug image if requested
        if debug:
            debug_path = os.path.join(BASE_DIR, f"debug_{region_name}.png")
            processed_img.save(debug_path)
            print(f"Debug image saved to: {debug_path}")
        
        # Configure Tesseract for number-only recognition
        custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
        
        # Perform OCR
        text = pytesseract.image_to_string(processed_img, config=custom_config)
        
        # Clean and parse the result
        rank_str = ''.join(filter(str.isdigit, text.strip()))
        
        if rank_str:
            try:
                rank = int(rank_str)
                if debug:
                    print(f"Detected Rank: {rank}")
                return rank
            except ValueError:
                if debug:
                    print(f"Could not parse rank from: {text}")
                return None
        else:
            if debug:
                print(f"No rank detected. OCR output: '{text}'")
            return None
    
    def extract_rank_safe(self, validate_screen=True, debug=False):
        """
        Extract rank with screen validation to prevent false positives
        Only returns rank if we're confirmed to be on main menu
        
        Args:
            validate_screen: If True, validates we're on main menu first
            debug: Save debug images
        
        Returns:
            Integer rank or None
        """
        if validate_screen:
            if not self.is_on_main_menu(validation_method="auto", debug=debug):
                if debug:
                    print("Not on main menu - skipping rank detection")
                return None
        
        return self.extract_rank(debug=debug)
    
    def extract_text(self, region_name, debug=False, silent=False):
        """
        Extract any text from a screen region
        
        Args:
            region_name: Name of the region to scan
            debug: If True, save debug images
            silent: If True, suppress "No text detected" messages
            
        Returns:
            String of detected text or None
        """
        # Capture the region
        img = self.capture_region(region_name)
        if img is None:
            return None
        
        # Preprocess for OCR
        processed_img = self.preprocess_for_ocr(img, for_numbers=False)
        
        # Save debug image if requested
        if debug:
            debug_path = os.path.join(BASE_DIR, f"debug_{region_name}.png")
            processed_img.save(debug_path)
            print(f"Debug image saved to: {debug_path}")
        
        # Perform OCR
        text = pytesseract.image_to_string(processed_img)
        
        # Clean the result
        text = text.strip()
        
        if text:
            if not silent:
                print(f"Detected Text: {text}")
            return text
        else:
            if not silent:
                print("No text detected")
            return None
    
    def get_rank_with_retry(self, max_attempts=3, delay=0.5, validate_screen=True):
        """
        Try to get rank multiple times with delay between attempts
        
        Args:
            max_attempts: Number of times to try
            delay: Seconds to wait between attempts
            validate_screen: If True, only return rank if on main menu
            
        Returns:
            Rank number or None
        """
        import time
        
        for attempt in range(max_attempts):
            if validate_screen:
                rank = self.extract_rank_safe(validate_screen=True, debug=False)
            else:
                rank = self.extract_rank(debug=False)
            
            if rank is not None:
                return rank
            if attempt < max_attempts - 1:
                time.sleep(delay)
        
        return None


def test_rank_detection():
    """Test function to verify rank detection is working"""
    print("Testing Rank Detection...")
    print("=" * 50)
    
    detector = RankDetector()
    
    # Check if regions are configured
    if not detector.regions:
        print("ERROR: No regions configured!")
        print("Please run SetupRegions.py first to define screen regions.")
        return
    
    print(f"Loaded regions: {list(detector.regions.keys())}")
    print()
    
    # Try to detect rank
    print("Attempting to detect rank (with debug images)...")
    rank = detector.extract_rank(debug=True)
    
    if rank:
        print(f"\n✓ SUCCESS: Detected rank = {rank}")
    else:
        print(f"\n✗ FAILED: Could not detect rank")
        print("Check debug_rank.png to see what was captured")
    
    print("=" * 50)


if __name__ == "__main__":
    test_rank_detection()
