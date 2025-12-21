# Screen Validation Setup Guide

## Why Validation?
Prevents false rank detection when numbers appear on other screens (deck builder, card counts, etc.)

## Methods Available

### 1. **Auto Validation** (Recommended) ⭐
Combines multiple checks - safest option.

### 2. **Menu Text Detection**
Looks for menu buttons like "PLAY", "SHOP", "CARDS"

### 3. **Template Matching**
Compares against a saved screenshot of a unique UI element

### 4. **Pixel Color Checking**
Checks if specific pixels are expected colors

---

## Quick Setup (Auto Validation)

### Step 1: Define Menu Text Region (Optional but Recommended)

1. Open Pokemon TCG Live to **main menu**
2. Run `SetupRegions.py`
3. Detect game window
4. Take screenshot
5. Select region name: **`menu_text`**
6. Select an area containing menu buttons (PLAY, SHOP, etc.)
7. Save

**What it does:**
- Looks for menu text before detecting rank
- If "PLAY" or "SHOP" found → Main menu confirmed → Rank detection proceeds
- If not found → Different screen → Rank detection skipped

### Step 2: Use Safe Detection

```python
from RankDetector import RankDetector

detector = RankDetector()

# Safe method - validates screen first
rank = detector.extract_rank_safe(validate_screen=True, debug=True)

if rank:
    print(f"Rank: {rank} (validated!)")
else:
    print("Not on main menu or rank not visible")
```

**That's it!** The system now:
1. Checks if menu text is present
2. Verifies rank is a reasonable number (1-99999)
3. Only returns rank if both pass

---

## Advanced: Template Matching Setup

For even more precision, you can use a template image.

### Step 1: Capture Template

1. Open game to main menu
2. Take a screenshot
3. Crop a **small, unique UI element** that ONLY appears on main menu:
   - Game logo in corner
   - Specific button or icon
   - Decorative element
   - **Size: 50x50 to 200x200 pixels works well**

4. Save as: `templates/main_menu_indicator.png`

### Step 2: Create Templates Folder

```
BattleLogImport/
  templates/
    main_menu_indicator.png    ← Your template
```

### Step 3: Use Template Validation

The system will automatically use the template if it exists!

```python
detector = RankDetector()

# Auto validation now includes template matching
rank = detector.extract_rank_safe(validate_screen=True)
```

---

## Advanced: Pixel Color Checking

For ultimate precision, check specific pixel colors.

### Example: Check if rank background is expected color

```python
detector = RankDetector()

# Define expected pixels (x, y within region, RGB color, tolerance)
expected = [
    (5, 5, (255, 255, 255), 30),    # Top-left should be white-ish
    (100, 10, (0, 120, 215), 40),   # Mid should be blue-ish
]

if detector.check_pixel_colors("rank", expected):
    print("Pixels match - likely on main menu")
    rank = detector.extract_rank()
```

**How to find pixel colors:**
1. Open debug_rank.png in image editor
2. Use color picker to find RGB values
3. Add some tolerance (20-40) for slight variations

---

## Validation Modes

```python
detector = RankDetector()

# Mode 1: Auto (recommended) - Multiple validations
on_menu = detector.is_on_main_menu(validation_method="auto", debug=True)

# Mode 2: Text only - Just look for menu text
on_menu = detector.is_on_main_menu(validation_method="text")

# Mode 3: Template only - Just use template matching
on_menu = detector.is_on_main_menu(validation_method="template")

# Mode 4: Any - Accept if ANY validation passes (less strict)
on_menu = detector.is_on_main_menu(validation_method="any")

# Mode 5: Rank only - Just check if rank is valid number
on_menu = detector.is_on_main_menu(validation_method="rank")
```

---

## Post-Battle Detection

To detect rank on the **post-battle screen** (different layout):

### Option 1: Define separate regions
```json
{
    "rank": { ... },              // Main menu rank
    "rank_postbattle": { ... },   // Post-battle rank
    "postbattle_text": { ... }    // "VICTORY" or "DEFEAT" text
}
```

### Option 2: Detect battle result text first
```python
detector = RankDetector()

# Check if on post-battle screen
if detector.validate_screen_by_text("postbattle_text", ["VICTORY", "DEFEAT"]):
    print("On post-battle screen!")
    rank = detector.extract_rank("rank_postbattle")
```

---

## Testing Validation

```python
from RankDetector import RankDetector

detector = RankDetector()

print("Testing screen validation...")

# Test with debug to see what's happening
is_menu = detector.is_on_main_menu(validation_method="auto", debug=True)

if is_menu:
    print("✓ Validated: On main menu")
    rank = detector.extract_rank(debug=True)
else:
    print("✗ Not on main menu")
```

**Debug output shows:**
```
  Menu text validation: True
  Rank validation: True (rank=1234)
✓ Validated: On main menu
```

---

## Recommended Setup

### Minimum (Good):
1. Define `rank` region
2. Use `extract_rank_safe(validate_screen=True)`
3. System checks if rank is valid number

### Recommended (Better):
1. Define `rank` region
2. Define `menu_text` region (containing PLAY button)
3. Use `extract_rank_safe(validate_screen=True)`
4. System checks menu text + valid rank

### Advanced (Best):
1. Define `rank` region
2. Define `menu_text` region
3. Create template image in `templates/main_menu_indicator.png`
4. Use `extract_rank_safe(validate_screen=True)`
5. System checks template + menu text + valid rank

---

## Examples in Your Workflow

### Example 1: After Battle Log
```python
# In your battle log monitor
def after_battle_detected():
    detector = RankDetector()
    
    # Wait for screen to settle
    time.sleep(2)
    
    # Try to detect with validation
    rank = detector.extract_rank_safe(validate_screen=True, debug=True)
    
    if rank:
        print(f"Rank detected: {rank}")
        return rank
    else:
        print("Not on main menu yet or rank not visible")
        return None
```

### Example 2: Continuous Monitoring
```python
def monitor_for_rank():
    detector = RankDetector()
    
    while True:
        # Only detect if on main menu
        if detector.is_on_main_menu(validation_method="auto"):
            rank = detector.extract_rank()
            if rank:
                print(f"On main menu, rank: {rank}")
                return rank
        
        time.sleep(5)  # Check every 5 seconds
```

---

## Summary

**Without Validation:**
```python
rank = detector.extract_rank()
# Might detect ANY number on screen
```

**With Validation:**
```python
rank = detector.extract_rank_safe(validate_screen=True)
# Only detects rank when confirmed on main menu
```

**Best Practice:**
1. Define `menu_text` region with PLAY/SHOP buttons
2. Use `extract_rank_safe()` always
3. Add template if needed for extra precision

This prevents false positives from:
- Card counts in deck builder
- Damage numbers in battles
- Collection numbers
- Any other numbers on screen
