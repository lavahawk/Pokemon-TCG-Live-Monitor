---
tags: [module]
files: [RankDetector.py, BattleState.py, screen_regions.json]
---
# RankDetector.py + BattleState.py: screen reading

## RankDetector (617 lines)
- Finds Tesseract: `tesseract/`, `.tesseract/`, `Tesseract-OCR/`, Program Files, PATH.
- `find_game_window()`: EnumWindows for a visible title **containing** "Pokémon TCG Live" (BUG-025), else by process `Pokemon TCG Live.exe`. Uses `GetWindowRect` (incl. border). DPI: mss sets the process DPI-aware on first instance, so coords are physical; OK.
- Regions in `screen_regions.json` are percentages of the window (`rank`, `my_deck_name`, `menu_text`). `capture_region` rejects negative left/top (BUG-026).
- OCR: grayscale → Otsu → `fastNlMeansDenoising` → 2× cubic → Tesseract (`--psm 7` digits-only for rank).
- `is_on_main_menu("auto")` needs rank + deck text + menu words. `extract_rank_safe` re-runs all of it, so about 8 Tesseract calls per detection (perf).
- Holds `self.sct = mss.mss()` forever (BUG-010).

## BattleState (152 lines)
- `check_hud()` samples three 6×6 px patches (chat bubble white @ (2.2%, 59%), prize badge yellow @ (22.5%, 86.2%), timer panel dark @ (97.5%, 30%)); ≥2 of 3 = in battle. Tuned on 1366×768.
- Logs show the prize check is usually `N`, so detection relies on chat + timer; the HUD "gone" fires mid-battle often (cards covering anchors), which is why the watcher only arms on it.
- Constructs a new `RankDetector()` per call (BUG-010).

Related: BUG-010, 020, 021, 025, 026.
