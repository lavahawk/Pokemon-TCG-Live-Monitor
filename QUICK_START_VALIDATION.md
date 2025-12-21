# Quick Start: Screen Validation

## Goal
Prevent false positives when detecting rank - only detect when on the main menu or post-battle screen.

## Setup (Choose ONE method)

### Option 1: Menu Text Detection (Easiest)
**Best for: Beginners, quick setup**

1. Open Pokemon TCG Live to the main menu
2. Run `SetupRegions.py`
3. Select "menu_text" from the dropdown
4. Draw a box around the **PLAY** button (or SHOP, CARDS - any menu button)
5. Click "Save Regions"

**Test it:**
```python
python Test_Validation.py
# Choose option 1
```

### Option 2: Template Matching (Most Accurate)
**Best for: Maximum precision**

1. Open Pokemon TCG Live to the main menu
2. Run `CaptureTemplate.py`
3. Click "Take Screenshot"
4. Select a **small, unique** UI element that ONLY appears on the main menu
   - Good examples: Logo, specific icon, decorative element
   - Bad examples: Generic buttons, text that appears elsewhere
5. Click "Save Template" and name it (e.g., `main_menu_indicator.png`)

**Test it:**
```python
python Test_Validation.py
# Choose option 2
```

### Option 3: Pixel Color Check (Advanced)
**Best for: Developers who want precise control**

Manually edit `screen_regions.json` and add pixel color checks. See `SCREEN_VALIDATION_GUIDE.md` for details.

---

## Using Validation in Code

### Safe Rank Detection
```python
from RankDetector import RankDetector

detector = RankDetector()

# This will ONLY return a rank if validation passes
rank = detector.extract_rank_safe(validate_screen=True, debug=True)

if rank:
    print(f"Rank detected: {rank}")
else:
    print("Not on main menu - no detection")
```

### Manual Validation Check
```python
from RankDetector import RankDetector

detector = RankDetector()

# Check if we're on the main menu
if detector.is_on_main_menu(validation_method="auto", debug=True):
    # Only proceed if validation passes
    rank = detector.extract_rank()
    print(f"Rank: {rank}")
else:
    print("Not on main menu - skipping detection")
```

---

## Testing

Run the comprehensive test:
```bash
python Test_Validation.py
# Choose option 4 (Auto Validation)
```

**Follow the prompts:**
1. Position game on main menu → Should detect rank ✓
2. Switch to deck builder → Should NOT detect (blocked) ✓
3. Switch to collection → Should NOT detect (blocked) ✓

---

## Validation Methods

| Method | Pros | Cons | Recommended For |
|--------|------|------|----------------|
| **Text Detection** | Easy setup, works well | Requires menu_text region | Most users |
| **Template Matching** | Most accurate, precise | Need to capture template | Best accuracy |
| **Pixel Colors** | Very fast | Manual configuration | Advanced users |
| **Auto (All)** | Best reliability | Slightly slower | Production use |

---

## Troubleshooting

### "No menu_text region configured"
→ Run `SetupRegions.py` and create a menu_text region around a menu button

### "Template not found"
→ Run `CaptureTemplate.py` to create a template image

### Still getting false positives
→ Use **template matching** instead of text detection
→ Choose a more unique template element
→ Combine multiple validation methods (auto mode)

### Validation blocking legitimate detections
→ Run with `debug=True` to see why validation failed
→ Adjust threshold values (see SCREEN_VALIDATION_GUIDE.md)
→ Make menu_text region larger to capture more text

---

## Next Steps

After validation is working:

1. **Integrate into TCGLiveMonitor.py**
   - Add rank detection after battle log is detected
   - Save rank to Excel with battle data

2. **Add deck name detection**
   - Use same validation approach
   - Detect actual deck name instead of AI guessing

3. **Post-Battle Detection**
   - Create templates for post-battle screen
   - Validate before extracting rank/deck

See `SCREEN_VALIDATION_GUIDE.md` for detailed examples and advanced usage.
