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
from PIL import Image

# Get the script's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REGIONS_CONFIG = os.path.join(BASE_DIR, "screen_regions.json")
RANK_PAD_Y = 0.35  # see extract_rank()


def _find_tesseract():
    """Locate the Tesseract OCR executable.

    Checks (in order):
      1. A portable Tesseract bundled in the app folder (e.g. ``tesseract/``
         or ``.tesseract/``) — used by the portable/no-admin build.
      2. The standard system install path.
      3. Any ``tesseract.exe`` on PATH.
    Returns the path string, or the default system path as a last resort.
    """
    candidates = [
        os.path.join(BASE_DIR, "tesseract", "tesseract.exe"),
        os.path.join(BASE_DIR, ".tesseract", "tesseract.exe"),
        os.path.join(BASE_DIR, "Tesseract-OCR", "tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    # Fall back to PATH lookup.
    import shutil
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    return r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# Configure Tesseract path (portable-first, then system).
pytesseract.pytesseract.tesseract_cmd = _find_tesseract()


class RankDetector:
    """Handles OCR-based rank detection from screen regions"""
    
    def __init__(self):
        self.regions = self.load_regions()
        # No long-lived mss instance: mss holds GDI handles until close()
        # and is thread-bound (BUG-010). Captures open a short-lived one.
        self.game_window = None
        self.screen_validators = {}  # Cache for screen validation templates
    
    def load_regions(self):
        """Load saved screen regions from config file"""
        if os.path.exists(REGIONS_CONFIG):
            with open(REGIONS_CONFIG, 'r') as f:
                return json.load(f)
        return {}
    
    def find_game_window(self):
        """
        Find the Pokemon TCG Live game window (exact title match).

        Returns:
            dict {'hwnd','title','left','top','width','height'} or None
        """
        from game_window import game_rect
        self.game_window = game_rect()
        return self.game_window

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
    
    def capture_region(self, region_name, pad_y=0.0):
        """
        Capture a specific screen region
        Automatically finds game window and adjusts coordinates

        Args:
            region_name: Name of the region defined in config
            pad_y: extra height above AND below, as a fraction of the region's
                   own height (so it scales with the window like the region)

        Returns:
            PIL Image of the captured region or None if region not found
        """
        # Get absolute coordinates (handles both relative and absolute regions)
        abs_region = self.get_absolute_region(region_name)
        if not abs_region:
            return None
        if pad_y:
            extra = int(round(abs_region["height"] * pad_y))
            abs_region = dict(abs_region, top=abs_region["top"] - extra,
                              height=abs_region["height"] + 2 * extra)
        
        # Validate region bounds
        if abs_region["width"] <= 0 or abs_region["height"] <= 0:
            return None
        
        # Negative coordinates are valid on multi-monitor setups (a monitor
        # left of / above the primary one), so they are NOT rejected.
        
        # Capture the screen region
        monitor = {
            "top": abs_region["top"],
            "left": abs_region["left"],
            "width": abs_region["width"],
            "height": abs_region["height"]
        }
        
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return img
        except Exception:
            return None
    
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
    
    @staticmethod
    def preprocess_rank(image):
        """Isolate the rank digits (white on the dark rank banner).

        Keeps bright pixels only, then keeps connected shapes at least half
        as tall as the tallest one (the digits share one height), which drops
        specks, the banner's edge highlights and the league badge rim that
        Otsu thresholding let through ("1446" read as "61446"). The digits
        are cropped and scaled to a fixed ~48 px height, so the result is the
        same at any window size.
        """
        gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        mask = (gray >= 170).astype(np.uint8)
        count, _labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if count <= 1:
            return None
        heights = stats[1:, cv2.CC_STAT_HEIGHT]
        tallest = heights.max()
        if tallest < 6:
            return None
        keep = np.zeros_like(mask)
        for i in range(1, count):
            x, y, w, h, area = stats[i]
            if h >= 0.5 * tallest and w <= 1.5 * tallest and area >= 4:
                keep[_labels == i] = 1
        ys, xs = np.nonzero(keep)
        if len(xs) == 0:
            return None
        # Upscale the GRAYSCALE digits (not the binary mask) so small windows
        # keep the digit shapes, then threshold. Non-digit pixels are blanked.
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        digits = np.where(cv2.dilate(keep, np.ones((3, 3), np.uint8))[y0:y1, x0:x1] > 0,
                          gray[y0:y1, x0:x1], 0).astype(np.uint8)
        scale = 48.0 / digits.shape[0]
        digits = cv2.resize(digits, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        crop = np.where(digits >= 150, 0, 255).astype(np.uint8)   # black digits on white
        crop = cv2.copyMakeBorder(crop, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)
        return Image.fromarray(crop)

    def extract_rank(self, region_name="rank", debug=False):
        """
        Extract rank number from screen
        
        Args:
            region_name: Name of the region to scan
            debug: If True, save debug images
            
        Returns:
            Integer rank number or None if not detected
        """
        # Capture the region. Padded vertically by 35% of its height each
        # side: in Master league the points number sits higher than the Elo
        # number of the lower leagues, and the calibrated box clipped the
        # digit tops. Relative to the region, so resolution-independent.
        img = self.capture_region(region_name, pad_y=RANK_PAD_Y)
        if img is None:
            return None

        # Preprocess for OCR (digit isolation; generic fallback)
        processed_img = self.preprocess_rank(img) or self.preprocess_for_ocr(img, for_numbers=True)

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


def read_rank_confirmed(detector, last_accepted=None, reads=2, delay=1.0, big_jump=100, debug=False):
    """Read the rank several times and only accept a stable, plausible value.

    OCR occasionally drops or adds a digit (e.g. 151 -> 3, 260 -> 2600). A
    value is accepted when `reads` consecutive reads agree; a jump of more
    than `big_jump` from the last accepted rank needs one extra agreeing read.
    Returns the rank or None.
    """
    import time as _time
    values = []
    needed = reads
    for _ in range(reads + 2):
        value = detector.extract_rank(debug=debug)
        if value is not None and 0 < value < 5000:
            values.append(value)
        if last_accepted is not None and values and abs(values[-1] - last_accepted) > big_jump:
            needed = reads + 1
        if len(values) >= needed and len(set(values[-needed:])) == 1:
            return values[-1]
        _time.sleep(delay)
    return None


def snap_deck_name(raw_name, known_names, cutoff=0.82):
    """Map an OCR'd deck name onto an already-known deck name when close.

    OCR turns "Dragapult" into "Oragaputt" now and then, which used to create
    a brand-new deck in the stats. Returns the best known name with a
    similarity >= cutoff, otherwise the cleaned raw name.
    """
    import difflib
    cleaned = " ".join((raw_name or "").split())
    if not cleaned:
        return None
    known = [k for k in (known_names or []) if k]
    if cleaned in known:
        return cleaned
    lower_map = {k.casefold(): k for k in known}
    matches = difflib.get_close_matches(cleaned.casefold(), list(lower_map.keys()), n=1, cutoff=cutoff)
    return lower_map[matches[0]] if matches else cleaned


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
        print("\n✗ FAILED: Could not detect rank")
        print("Check debug_rank.png to see what was captured")
    
    print("=" * 50)


if __name__ == "__main__":
    test_rank_detection()
