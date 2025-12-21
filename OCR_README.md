# OCR Rank Detection Feature

## Overview
This feature adds screen-based OCR (Optical Character Recognition) to detect your rank from the Pokemon TCG Live main menu. It works at any resolution and can be extended to capture other on-screen information.

## How It Works
1. **Region Setup**: You define screen regions where text/numbers appear
2. **Screen Capture**: The system captures those specific regions
3. **OCR Processing**: Text is extracted using Tesseract OCR
4. **Data Recording**: Detected values are saved to your Excel sheet

## Installation

### Step 1: Install Python Dependencies
Run the installation script:
```
Install_Dependencies.bat
```

Or manually install:
```
pip install -r requirements.txt
```

### Step 2: Install Tesseract OCR
Tesseract is required for text recognition.

1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
2. Run the installer
3. Install to: `C:\Program Files\Tesseract-OCR` (default location)
4. Add to PATH if prompted

**Note**: If you install Tesseract to a different location, edit line 17 in `RankDetector.py`:
```python
pytesseract.pytesseract.tesseract_cmd = r'C:\Your\Custom\Path\tesseract.exe'
```

## Setup Instructions

### 1. Define Screen Regions
You need to tell the system WHERE to look for rank on your screen.

1. Open Pokemon TCG Live and navigate to the **main menu** (where rank is visible)
2. Run `SetupRegions.py`:
   ```
   python SetupRegions.py
   ```
3. Click **"Take Screenshot"** in the tool
4. Click and drag to select the area where **the rank number** appears
5. Make sure "rank" is selected in the Region Name dropdown
6. Click **"Save Configuration"**

**Tips for defining regions:**
- Make the region as small as possible while still capturing all digits
- Include some padding around the number (a few pixels)
- Avoid including other text or graphics
- The region is saved in absolute coordinates, so it works at any resolution

### 2. Test Detection
After defining regions:

1. In the SetupRegions tool, click **"Test Rank Detection"**
2. Or run directly:
   ```
   python RankDetector.py
   ```

This will:
- Capture the rank region
- Process it for OCR
- Save a debug image (`debug_rank.png`)
- Print the detected rank

**If detection fails:**
- Check `debug_rank.png` to see what was captured
- Adjust the region if needed (rerun SetupRegions.py)
- Make sure the rank number is clearly visible on screen
- Try adjusting the game's graphics settings for better text clarity

## Usage in Your Scripts

### Basic Rank Detection
```python
from RankDetector import RankDetector

detector = RankDetector()

# Detect rank
rank = detector.extract_rank()
if rank:
    print(f"Your rank: {rank}")
```

### Check if on Main Menu
```python
detector = RankDetector()

if detector.is_on_main_menu():
    print("On main menu!")
    rank = detector.extract_rank()
```

### Retry Logic
```python
detector = RankDetector()

# Try 3 times with 0.5s delay
rank = detector.get_rank_with_retry(max_attempts=3, delay=0.5)
```

### Debug Mode
```python
detector = RankDetector()

# Enable debug to save capture images
rank = detector.extract_rank(debug=True)
# Check debug_rank.png to see what was captured
```

## Configuration

### Region Configuration File
Regions are stored in `screen_regions.json`:
```json
{
    "rank": {
        "top": 100,
        "left": 200,
        "width": 150,
        "height": 50
    }
}
```

You can manually edit this file if needed, but it's easier to use SetupRegions.py.

### Adding More Regions
You can define multiple regions for different screen elements:

1. Run `SetupRegions.py`
2. Change Region Name dropdown to:
   - `username` - Your username
   - `deck_name` - Current deck name
   - `custom` - Any custom region
3. Take screenshot and define region
4. Save configuration

Then in your code:
```python
# Detect different regions
username = detector.extract_text("username")
deck = detector.extract_text("deck_name")
```

## Integration with Main Monitor

To integrate rank detection into your battle log monitor:

1. Import the detector in `BackgroundRun/TCGLiveMonitor.py`
2. Check for rank when game starts
3. Save rank with battle log data

Example integration point:
```python
from RankDetector import RankDetector

# In wait_for_game_startup():
def wait_for_game_startup():
    print("Waiting for Pokémon TCG Live to start...")
    while not is_pokemon_tcg_live_running():
        time.sleep(10)
    
    print("Game detected! Waiting for main menu...")
    time.sleep(5)  # Give game time to load
    
    # Detect rank
    detector = RankDetector()
    rank = detector.get_rank_with_retry(max_attempts=3, delay=1)
    if rank:
        print(f"Detected Rank: {rank}")
        # Save to Excel or log file
    
    print("Monitoring clipboard...")
```

## Troubleshooting

### "No regions configured" error
- Run `SetupRegions.py` first to define regions
- Make sure `screen_regions.json` exists

### Rank not detected / Wrong numbers
- Run with `debug=True` to see captured image
- Check if rank is clearly visible on screen
- Adjust region in SetupRegions.py
- Make sure game graphics are at good quality
- Try different font sizes in game settings

### "Import 'pytesseract' could not be resolved"
- Install Tesseract OCR application (not just Python package)
- Verify installation path in RankDetector.py

### Detection works sometimes but not always
- Game menu might be loading/animating
- Use retry logic: `get_rank_with_retry()`
- Add small delay before detection

### Wrong region captured
- Screen resolution may have changed
- Re-run SetupRegions.py to redefine regions
- Regions are in absolute coordinates, not relative

## Future Enhancements

Possible additions:
- Detect opponent's username
- Capture deck name from deck selection screen
- Monitor win/loss streak
- Track daily quests completion
- Detect current coins/crystals

All can be added by:
1. Defining new regions in SetupRegions.py
2. Using `detector.extract_text("region_name")`

## Files Added

- `RankDetector.py` - Core OCR detection module
- `SetupRegions.py` - Interactive region setup tool
- `screen_regions.json` - Region configuration (created on first setup)
- `requirements.txt` - Updated with OCR dependencies
- `Install_Dependencies.bat` - Installation script
- `OCR_README.md` - This documentation

## Technical Details

**OCR Engine**: Tesseract 5.x
**Screen Capture**: mss (fast multi-screen capture)
**Image Processing**: OpenCV
**Preprocessing Steps**:
1. Convert to grayscale
2. Threshold to binary image
3. Denoise
4. Upscale 2x for better OCR

**OCR Configuration for Numbers**:
- Whitelist: 0-9 only
- PSM Mode: 7 (single text line)
- OEM Mode: 3 (default)
