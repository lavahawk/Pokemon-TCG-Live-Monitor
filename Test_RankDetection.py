"""
Quick Test Script for Rank Detection
Run this to verify your OCR setup is working
"""

import os
import sys

def check_dependencies():
    """Check if all required packages are installed"""
    print("Checking dependencies...")
    print("=" * 50)
    
    missing = []
    
    try:
        import cv2
        print("✓ OpenCV installed")
    except ImportError:
        print("✗ OpenCV NOT installed")
        missing.append("opencv-python")
    
    try:
        import mss
        print("✓ MSS installed")
    except ImportError:
        print("✗ MSS NOT installed")
        missing.append("mss")
    
    try:
        import pytesseract
        print("✓ Pytesseract installed")
        
        # Set Tesseract path
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        
        # Try to get Tesseract version
        try:
            version = pytesseract.get_tesseract_version()
            print(f"  Tesseract version: {version}")
        except Exception as e:
            print(f"  ⚠ Warning: Tesseract executable not found or not in PATH")
            print(f"  Please install Tesseract OCR from:")
            print(f"  https://github.com/UB-Mannheim/tesseract/wiki")
            missing.append("tesseract-ocr")
    except ImportError:
        print("✗ Pytesseract NOT installed")
        missing.append("pytesseract")
    
    try:
        from PIL import Image
        print("✓ Pillow installed")
    except ImportError:
        print("✗ Pillow NOT installed")
        missing.append("Pillow")
    
    print("=" * 50)
    
    if missing:
        print("\n⚠ MISSING DEPENDENCIES:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\nRun: Install_Dependencies.bat")
        print("Or: pip install -r requirements.txt")
        return False
    else:
        print("\n✓ All dependencies installed!")
        return True


def check_config():
    """Check if regions are configured"""
    print("\nChecking configuration...")
    print("=" * 50)
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(BASE_DIR, "screen_regions.json")
    
    if os.path.exists(config_file):
        print(f"✓ Configuration file found: {config_file}")
        
        import json
        with open(config_file, 'r') as f:
            regions = json.load(f)
        
        if regions:
            print(f"✓ {len(regions)} region(s) defined:")
            for name, region in regions.items():
                if region.get('relative', False):
                    # Check if percentage-based (v2.0) or pixel-based (old)
                    if 'percent_x' in region:
                        print(f"  - {name}: {region['percent_width']:.1%} x {region['percent_height']:.1%} (percentage-based, scales!)")
                    else:
                        print(f"  - {name}: {region.get('width', '?')}x{region.get('height', '?')} (pixel-based)")
                else:
                    # Old absolute format
                    print(f"  - {name}: {region.get('width', '?')}x{region.get('height', '?')} (old absolute format)")
            return True
        else:
            print("✗ No regions defined in config")
            return False
    else:
        print(f"✗ Configuration file not found")
        print(f"  Expected: {config_file}")
        return False


def test_detection():
    """Test rank detection"""
    print("\nTesting rank detection...")
    print("=" * 50)
    print("IMPORTANT: Make sure Pokemon TCG Live is open")
    print("           and showing the MAIN MENU with your rank visible!")
    print("=" * 50)
    
    input("Press Enter when ready to test...")
    
    try:
        from RankDetector import RankDetector
        import json
        
        detector = RankDetector()
        
        # Show window and region info
        window = detector.find_game_window()
        if window:
            print(f"\n✓ Found game window:")
            print(f"  Title: {window.get('title', 'Unknown')}")
            print(f"  Size: {window['width']}x{window['height']}")
            
            # Show region scaling info
            if os.path.exists('screen_regions.json'):
                with open('screen_regions.json', 'r') as f:
                    regions = json.load(f)
                
                if 'rank' in regions:
                    rank_region = regions['rank']
                    print(f"\n📐 Rank region configuration:")
                    
                    if 'percent_x' in rank_region:
                        # Calculate scaled position
                        calc_x = int(window['width'] * rank_region['percent_x'])
                        calc_y = int(window['height'] * rank_region['percent_y'])
                        calc_w = int(window['width'] * rank_region['percent_width'])
                        calc_h = int(window['height'] * rank_region['percent_height'])
                        
                        print(f"  Percentage-based: {rank_region['percent_x']:.1%} x {rank_region['percent_y']:.1%}")
                        print(f"  Scaled to: ({calc_x}, {calc_y}) size {calc_w}x{calc_h}")
                        print(f"  ✅ Will scale with any resolution!")
                    else:
                        print(f"  Fixed pixels: ({rank_region.get('offset_x', '?')}, {rank_region.get('offset_y', '?')})")
                        print(f"  ⚠️  Won't scale with resolution changes")
                        print(f"  Run SetupRegions.py to update to percentage-based")
        else:
            print(f"\n⚠️  Game window not found!")
        
        print("\nAttempting to detect rank...")
        rank = detector.extract_rank(debug=True)
        
        print("\n" + "=" * 50)
        if rank:
            print(f"✓ SUCCESS!")
            print(f"  Detected Rank: {rank}")
            print(f"\nDebug image saved to: debug_rank.png")
        else:
            print(f"✗ DETECTION FAILED")
            print(f"\nPossible issues:")
            print(f"  1. Game not on main menu")
            print(f"  2. Rank not visible on screen")
            print(f"  3. Region defined incorrectly")
            print(f"  4. Wrong resolution/window size")
            print(f"\nCheck debug_rank.png to see what was captured")
            print(f"If needed, run SetupRegions.py to redefine the region")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main test routine"""
    print("\n" + "=" * 50)
    print("RANK DETECTION TEST SCRIPT")
    print("=" * 50)
    
    # Step 1: Check dependencies
    if not check_dependencies():
        print("\n❌ Please install missing dependencies first!")
        input("\nPress Enter to exit...")
        return
    
    # Step 2: Check configuration
    if not check_config():
        print("\n❌ Please run SetupRegions.py first to define regions!")
        print("\nSteps:")
        print("1. Open Pokemon TCG Live to the main menu")
        print("2. Run: python SetupRegions.py")
        print("3. Take a screenshot and define the rank region")
        print("4. Save the configuration")
        input("\nPress Enter to exit...")
        return
    
    # Step 3: Test detection
    test_detection()
    
    print("\n")
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
