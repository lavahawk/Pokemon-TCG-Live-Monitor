---
tags: [dev]
updated: 2026-10-11
---
# Dev Environment and Test Harness

## Production environment (Lva's PC)
Windows 11 x64, project at `C:\Users\2awso\Downloads\BattleLogImport`, venv `.venv\`, Tesseract bundled in `tesseract\`. Git repo present (`.git`; remote `github.com/lavahawk/Pokemon-TCG-Live-Monitor`). Game window observed on a secondary monitor (rect ≈ 1899..3853 × 136..1273).

## How Phase 1 ran the code (off-Windows)
The review session ran in a Linux sandbox on **copies**; nothing on the PC was executed or changed.
- Python 3.12 venv with the pinned versions: `PySide6-Essentials==6.10.1` (no WebEngine), `matplotlib==3.8.2`, `numpy==1.26.4`, `pydantic==2.6.1`, `pandas==2.2.0`, openpyxl, requests, bs4, lxml, mss, opencv-python-headless, pytesseract, Pillow, pygame, psutil, pyperclip.
- `scripts/winstubs.py`: stubs `win32gui/win32process/win32con/win32api` (and tkinter if missing) so modules import. Don't stub `winreg`/`msvcrt` globally (stdlib `mimetypes`/`subprocess` pick them up); `startup_utils` is stubbed per-script instead.
- `QT_QPA_PLATFORM=offscreen` for Qt.

## Scripts (in `04 Dev/scripts/`)
| Script | Run from | What it does |
|---|---|---|
| `log_audit.py <app_dir>` | anywhere | Pulls `is_battle_log` / `parse_winner_from_log` out of the real modules via AST (no side effects), hashes every log, maps logs to DB rows, prints duplicate groups |
| `repro.py` | cwd = **copy** of app dir | Reproduces BUG-001, 002 (via data), 004, 005, 007, 008, 023, 024, 027 |
| `render_stats.py` | cwd = copy of app dir | Builds `StatsWindow` offscreen against the real DB and saves screenshots (`Attachments/shot_*.png`) |

On Windows you can run `repro.py` and `log_audit.py` directly with the project venv (remove the `winstubs` import lines). **Always on a copy of the folder.** `AIParseBattleLog` creates `tcg_battles.db` on import, and `rebuild_session_stats` rewrites data.

## Verified facts (so nobody re-checks them)
- matplotlib `use('Qt5Agg')` + PySide6 only: works (QT_API resolves to PySide6) on 3.8.2 and 3.11.
- All modules import cleanly with stubs; `AutoClicker` needs `pyautogui` (not in requirements).
- `test_rank_weighted.py` runs (prints only, no assertions).
- pyflakes: no undefined names; only unused vars, a duplicate dict key and one SyntaxWarning (`TCGLiveMonitor.py:194`).

## Phase 2 plan for tests
Turn `repro.py` cases into `pytest` tests under `tests/` that run on a temp copy of the DB; add a CI-able import smoke test that runs against the release manifest (catches BUG-003).
