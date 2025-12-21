# Quick Start Guide - OCR Rank Detection

## Step-by-Step Setup

### STEP 1: Install Dependencies

#### A. Install Python Packages
Double-click: `Install_Dependencies.bat`

This installs:
- OpenCV (image processing)
- Pytesseract (OCR wrapper)
- MSS (screen capture)
- Pillow (image handling)

#### B. Install Tesseract OCR
1. Go to: https://github.com/UB-Mannheim/tesseract/wiki
2. Download the Windows installer (tesseract-ocr-w64-setup-v5.x.x.exe)
3. Run installer
4. Install to: `C:\Program Files\Tesseract-OCR` (default)
5. ✓ Check "Add to PATH" if prompted

---

### STEP 2: Define Screen Region

#### A. Open Pokemon TCG Live
- Launch the game
- Navigate to **MAIN MENU**
- Make sure your **RANK** is visible on screen

#### B. Run Region Setup Tool
Double-click: `Run_SetupRegions.bat`

#### C. Capture and Define Region
1. In the setup tool, click **"📸 Take Screenshot"**
   - Tool captures your entire screen
   
2. Make sure "rank" is selected in the dropdown (should be default)

3. **Click and drag** on the screenshot to select the rank area:
   ```
   ┌─────────────────────────────┐
   │ Pokemon TCG Live            │
   │                             │
   │ PLAY                        │
   │                             │
   │ Rank: ┌────┐  ← Select this │
   │       │1234│    number only │
   │       └────┘                │
   └─────────────────────────────┘
   ```
   
   **Tips:**
   - Make selection **tight** around the number
   - Include small padding (2-3 pixels)
   - Don't include the "Rank:" label
   - Don't include decorative elements
   
4. Click **"💾 Save Configuration"**

5. Click **"Test Rank Detection"**
   - Should show: "Detected Rank: 1234"
   - If fails, check `debug_rank.png` and adjust region

---

### STEP 3: Test It Works

Double-click: `Run_TestRankDetection.bat`

Expected output:
```
================================================
RANK DETECTION TEST SCRIPT
================================================
Checking dependencies...
✓ OpenCV installed
✓ MSS installed
✓ Pytesseract installed
  Tesseract version: 5.x.x
✓ Pillow installed
✓ All dependencies installed!

Checking configuration...
✓ Configuration file found
✓ 1 region(s) defined:
  - rank: (1234, 567) 150x40

Testing rank detection...
Press Enter when ready to test...

Attempting to detect rank...
Detected Rank: 1234

✓ SUCCESS!
  Detected Rank: 1234
  Debug image saved to: debug_rank.png
================================================
```

---

### STEP 4: Integrate (Optional)

To add rank tracking to your battle log monitor:

Edit `BackgroundRun\TCGLiveMonitor.py` and add:

```python
# At the top with other imports
from RankDetector import RankDetector

# In wait_for_game_startup() function, after game is detected:
def wait_for_game_startup():
    print("Waiting for Pokémon TCG Live to start...")
    while not is_pokemon_tcg_live_running():
        time.sleep(10)
    
    print("Game detected! Checking rank...")
    time.sleep(5)  # Wait for menu to load
    
    # Detect rank
    detector = RankDetector()
    rank = detector.get_rank_with_retry(max_attempts=3, delay=1)
    if rank:
        print(f"Your current rank: {rank}")
        # TODO: Save rank to Excel or log
    
    print("Monitoring clipboard...")
```

Then rebuild the .exe:
```
cd BackgroundRun
Create Build Script - NoGUI.bat
```

---

## Troubleshooting

### ❌ "Tesseract not found"
- Install Tesseract OCR (see Step 1B)
- OR edit `RankDetector.py` line 17 with your Tesseract path

### ❌ "No regions configured"
- Run `Run_SetupRegions.bat` first
- Make sure you saved the configuration

### ❌ Rank detected incorrectly
- Run `Run_SetupRegions.bat` again
- Delete old "rank" region
- Redefine with tighter selection
- Make sure only numbers are in the selection

### ❌ "Import could not be resolved" errors in VS Code
- These are just linting warnings
- Run `Install_Dependencies.bat` to install packages
- Restart VS Code if needed

### ❌ Detection works sometimes
- Game might be loading/animating
- Use `get_rank_with_retry()` for better reliability
- Add small delay before detection

---

## What's in screen_regions.json?

After setup, you'll have a file like this:
```json
{
    "rank": {
        "top": 567,
        "left": 1234,
        "width": 150,
        "height": 40
    }
}
```

This tells the detector:
- **top**: Y coordinate on screen
- **left**: X coordinate on screen  
- **width**: How wide the region is
- **height**: How tall the region is

All in pixels, absolute coordinates.

---

## Adding More Regions

You can detect other things too!

### Example: Detect Username
1. Run `Run_SetupRegions.bat`
2. Change dropdown to "username"
3. Take screenshot
4. Select the username area
5. Save

Then in code:
```python
detector = RankDetector()
username = detector.extract_text("username")
```

### Example: Detect Current Deck
1. Go to deck selection screen in game
2. Run `Run_SetupRegions.bat`
3. Change dropdown to "deck_name"
4. Select the deck name area
5. Save

---

## Files Created

After setup, you'll have:
- `screen_regions.json` - Your region definitions
- `debug_rank.png` - Last captured rank region (when using debug mode)

---

## Next Steps

1. ✅ Test rank detection works
2. Integrate into your main monitor script
3. Add rank column to Excel sheet
4. Track rank changes over time
5. Set up alerts when rank changes

Enjoy automated rank tracking! 🎮📊
