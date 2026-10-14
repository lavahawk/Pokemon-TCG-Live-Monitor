---
tags: [module, automation]
files: [AutoClicker.py, ContinueBlocker.py, SetupAutoClicker.py, button_templates/]
---
# Battle-end automation

Goal: when a battle ends, click **BATTLE LOG** → **export** before the user hits **Continue**, so the log is copied automatically; cover Continue with a themed blocker meanwhile. Design history: [[Battle-End AutoClicker History]] (archive).

- `SetupAutoClicker.py`: fullscreen Tk screenshot of the **primary** monitor; drag a rectangle → `button_templates/<name>.png` (`battle_log`, `battle_log_export`).
- `AutoClicker`: `cv2.matchTemplate` TM_CCOEFF_NORMED ≥ 0.8 on the bottom half of the game window (per-call `with mss.mss()`, but `__init__` leaks one, BUG-010). Clicks: PostMessage "background" (Unity ignores it) or physical `pyautogui` (move → down → up → restore cursor). Templates are pixel-exact, so they break on resize/scale changes.
- `ContinueBlocker.py`: a separate Qt process with a topmost frameless card at rel (0.50, 0.955) size (0.32×0.11) of the window; follows the window every 200 ms; dismisses on `Logs/.blocker_dismiss` or after 30 s; `os._exit(0)` after fade.

Issues: BUG-012 (pyautogui missing), BUG-014 (races, double blockers, post-export re-click, missed battle), BUG-010.
Question for Lva: keep, simplify (watcher-only, single blocker), or drop?
