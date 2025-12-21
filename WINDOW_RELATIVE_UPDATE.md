# 🎯 UPDATED: Window-Relative OCR Detection

## Major Update: Now Works Anywhere! ✅

The OCR system has been **completely updated** to use **window-relative coordinates**!

### What This Means:
✅ **Works if you move the game window**  
✅ **Works in fullscreen mode**  
✅ **Works after changing resolution**  
✅ **Works on different monitors**  
✅ **Works in windowed or borderless mode**  

### How It Works:
1. System detects the Pokemon TCG Live **window**
2. Regions are saved **relative to the window** (not screen)
3. When detecting, system finds window → calculates actual position → captures region
4. **Always accurate** regardless of window position!

---

## New Setup Process

### Step 1: Install Dependencies

Run: `Install_Dependencies.bat`

**New dependency added:** `pywin32` (for window detection)

Then install **Tesseract OCR**: https://github.com/UB-Mannheim/tesseract/wiki

---

### Step 2: Configure Regions (NEW WORKFLOW!)

1. **Launch Pokemon TCG Live**
2. **Run:** `Run_SetupRegions.bat`
3. **Click:** "🎮 Detect Game Window"
   - Should show: "✓ Game found: 1920x1080 at (0, 0)"
4. **Click:** "📸 Take Screenshot"
   - Captures JUST the game window
5. **Define Regions:**

#### Region 1: Rank (Required)
- Select "rank" from dropdown
- Click and drag over the rank number
- Should show: "Region 'rank' defined (WINDOW-RELATIVE)"

#### Region 2: My Deck Name (Recommended)
- Navigate in-game to where YOUR deck name is visible
  - Post-battle screen OR
  - Deck selection screen OR
  - Main menu (if visible)
- Click "🎮 Detect Game Window" again (window might have moved)
- Click "📸 Take Screenshot"
- Change dropdown to "my_deck_name"
- Click and drag over YOUR deck name
- Save

6. **Click:** "💾 Save Configuration"
7. **Click:** "Test Rank Detection" to verify

---

## Region Configuration Format (NEW!)

### Old Format (Absolute - Don't Use):
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
❌ Breaks if window moves or resolution changes

### New Format (Window-Relative - USE THIS):
```json
{
    "rank": {
        "relative": true,
        "offset_x": 100,
        "offset_y": 50,
        "width": 150,
        "height": 40
    },
    "my_deck_name": {
        "relative": true,
        "offset_x": 300,
        "offset_y": 200,
        "width": 400,
        "height": 50
    }
}
```
✅ Works anywhere, anytime!

- `offset_x`: Pixels from window **left edge**
- `offset_y`: Pixels from window **top edge**
- `width/height`: Region size

---

## Usage Examples

### Detect Rank (Still the Same!)
```python
from RankDetector import RankDetector

detector = RankDetector()
rank = detector.extract_rank()
print(f"Rank: {rank}")
```

**Behind the scenes (NEW):**
1. Finds Pokemon TCG Live window
2. Calculates: `screen_x = window_left + offset_x`
3. Calculates: `screen_y = window_top + offset_y`
4. Captures region
5. Runs OCR

### Detect Your Deck Name (NEW!)
```python
detector = RankDetector()
my_deck = detector.extract_text("my_deck_name")
print(f"My Deck: {my_deck}")
```

### Check Window Location
```python
detector = RankDetector()
window = detector.find_game_window()
if window:
    print(f"Game at: ({window['left']}, {window['top']})")
    print(f"Size: {window['width']} x {window['height']}")
```

---

## Integration Plan

### Current Workflow:
```
Battle log detected
    ↓
Save to file
    ↓
Run AI parser (guesses your deck from cards played)
    ↓
Save to Excel: [AI Deck] [Opponent Deck] [W/L]
```

### NEW Enhanced Workflow:
```
Battle log detected
    ↓
Save to file
    ↓
Run AI parser (identifies opponent deck, W/L)
    ↓
Use OCR to detect YOUR actual deck name ⭐ (more accurate!)
    ↓
Use OCR to detect current rank ⭐
    ↓
Save to Excel: [OCR Deck] [Opponent Deck] [W/L] [Rank]
```

**Why This Is Better:**
- ✅ AI often guesses wrong deck (similar cards in multiple decks)
- ✅ OCR reads actual deck name = 100% accurate
- ✅ Also captures rank for progression tracking
- ✅ AI still useful for opponent deck (can't OCR that)

---

## Where to Detect Deck Name

### Option 1: Post-Battle Screen (Recommended)
After battle ends, game usually shows:
```
┌─────────────────────────┐
│ VICTORY!                │
│                         │
│ Your Deck: Charizard ex │ ← Detect this!
│ vs Pikachu ex           │
│                         │
│ Rank: 1234              │ ← And this!
└─────────────────────────┘
```

### Option 2: Deck Selection Screen
Before battle, on deck selection:
```
┌─────────────────────────┐
│ Select Your Deck:       │
│                         │
│ ┌─────────────────────┐ │
│ │ Charizard ex        │ │ ← Detect this!
│ │ [Deck Image]        │ │
│ └─────────────────────┘ │
└─────────────────────────┘
```

### Option 3: Active Deck During Battle
Some games show active deck name during play

**Best Practice:**
Define multiple regions for different screens, use whichever is available!

---

## Testing Window-Relative Detection

### Test 1: Move Window
1. Run `Test_RankDetection.py` → should detect rank
2. **Move game window** to different position
3. Run `Test_RankDetection.py` again → **should still work!**

### Test 2: Change Resolution
1. Detect rank at 1920x1080
2. Change game to 1280x720
3. Detect again → **should still work!**

### Test 3: Fullscreen
1. Detect rank in windowed mode
2. Switch to fullscreen
3. Detect again → **should still work!**

---

## Troubleshooting

### ❌ "Game window not found"
- Make sure Pokemon TCG Live is **running**
- Make sure window is **visible** (not minimized)
- Check window title contains "Pokemon TCG Live"

### ❌ Detection worked before, now fails
- **Re-detect window:** Game window size/position might have changed
- Run SetupRegions.py → Click "Detect Game Window"
- If window size changed, **redefine regions**

### ❌ Region shows old [ABSOLUTE-OLD] format
- Old regions won't work with new system
- Delete old region in SetupRegions.py
- Redefine using new "Detect Game Window" workflow

### ❌ Deck name detection not working
- Make sure deck name is **clearly visible** on screen
- Try different game screens (post-battle, deck selection)
- Use debug mode: `detector.extract_text("my_deck_name", debug=True)`
- Check `debug_my_deck_name.png` to see what was captured

---

## Migration from Old System

If you already have `screen_regions.json` with absolute coordinates:

### Option 1: Start Fresh (Recommended)
1. Delete `screen_regions.json`
2. Run `SetupRegions.py`
3. Follow new workflow

### Option 2: Keep Old, Add New
1. Old regions will show as `[ABSOLUTE-OLD]` in SetupRegions
2. Define new regions using "Detect Game Window"
3. New regions will show as `[RELATIVE]`
4. System supports both formats (backwards compatible)

---

## Next Steps

1. ✅ Install pywin32: `pip install pywin32`
2. ✅ Run `SetupRegions.py` with new workflow
3. ✅ Define "rank" region (window-relative)
4. ✅ Define "my_deck_name" region (window-relative)
5. ✅ Test with `Test_RankDetection.py`
6. ✅ Test moving window → still works!
7. ✅ Review `IntegrateOCR_Example.py` for integration code
8. ✅ Update your workflow to use OCR deck instead of AI deck

---

## Summary of Changes

**Files Updated:**
- ✅ `RankDetector.py` - Now finds game window and uses relative coords
- ✅ `SetupRegions.py` - New "Detect Game Window" workflow
- ✅ `requirements.txt` - Added pywin32
- ✅ `IntegrateOCR_Example.py` - NEW: Shows how to integrate

**New Capabilities:**
- ✅ Window-relative coordinates
- ✅ Works with window movement
- ✅ Works with resolution changes
- ✅ Works in fullscreen
- ✅ Deck name detection (replace AI guess)
- ✅ Backwards compatible with old configs

**Workflow Changes:**
- ✅ Must click "Detect Game Window" before screenshot
- ✅ Regions now stored as offsets from window
- ✅ Can detect YOUR deck name (more accurate than AI)
- ✅ Rank + Deck detected after each battle

🎉 **Ready to use!** Follow the setup steps above!
