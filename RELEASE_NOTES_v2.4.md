# Pokemon TCG Live Monitor v2.4

A reliability release. Every fix is tracked in `DevVault/03 Findings/Bug Register.md`.

## Auto-start and installation
- **Auto-start works again.** Launching at Windows login (hidden, `pythonw`) crashed immediately because the monitor read the console input that `pythonw` doesn't have. It now runs fully in the background, writes its output to `Logs\monitor.log`, idles at low CPU priority until Pokemon TCG Live opens, and starts the overlay only once the game is running.
- **New one-step setup.** `bootstrap_setup.ps1` finds Python 3.10–3.12, or installs Python 3.12 for your user account if none is found (the pinned packages don't install on Python 3.13). It then builds the `.venv`, installs the packages, sets up Tesseract, registers auto-start and launches the monitor. The Inno Setup installer, `INSTALL_COMPLETE_v2.4.bat` and the wizard installer all use it.
- **No admin rights needed.** Everything installs per user, and auto-start uses the registry Run key instead of an elevated scheduled task.
- **Installers include every module.** The v2.3 installers left out `japan_data.py`, `BattleState.py` and `ContinueBlocker.py`, so the dashboard couldn't open. Installers now use `*.py` / `release_manifest.txt`.

## Battle-end auto-export (reworked)
- Button matching works across window sizes and resolutions, and remembers where the button appears, so polling is cheap.
- Each end screen is handled exactly once. Exporting the log yourself is always respected, and nothing is clicked unless the game is the focused window.
- One Continue blocker per battle, no extra BATTLE LOG clicks after a manual export, and automatic re-clicks when the game swallows a click.
- `pyautogui` and `mouse` are no longer needed.
- New toggle: Dashboard → Advanced → "Auto-export the battle log…".

## Data accuracy
- **No more duplicate battles.** Each battle log is identified by a content hash stored in the database. Existing duplicates were removed (a backup is in `Backups\`).
- **Times are local.** Times are stored and shown in local time. Existing UTC rows are converted once, automatically, and daily W/L no longer moves to the wrong day after an edit.
- **Correct post-battle updates.** The post-battle rank/deck update goes to the battle that was just played, not "the newest row".
- **Rank OCR checks.** OCR ranks must read the same twice, and big jumps need an extra confirmation. One-off misreads (151→3) were removed from history, and Best Elo ignores single readings.
- **Deck name matching.** OCR'd deck names snap to your existing deck names ("Oragapult" → "Dragapult").
- **Logs saved as UTF-8.** "Pokémon" no longer becomes "Pok�mon".
- **Rank-weighted win rate fixed.** It now uses the real ladder leagues (Nest/Quick/Poké/Great/Ultra/Master). Previously every game got the same weight.
- **Win/Loss for any username.** Results are correct for names with dots, spaces or accents.
- **Tournament tagging works.** Limitless tournament games are tagged again (the flag is only set during a real match and expires).

## Limitless
- Auto check-in and match-chat polling actually start. A setup block had been indented into the wrong function.
- The embedded Limitless pages can no longer read your clipboard. Links opened from pages must be `https://`, and match pages must be on limitlesstcg.com.

## Dashboard
- Closing the dashboard during a meta refresh no longer risks crashing the overlay.
- The "Open OCR Test Window" and "Run AI Battle Log Parser" buttons work.
- Japan tab: data sources are discovered automatically (no longer frozen in August), the translation picks the most specific name, several wrong translations were fixed, AI translation is one batched request, and meaningless win-rate columns are hidden for Japanese finish data.
- The win-rate trend shows your last 30 played days.

## Privacy
- Ordinary copied text is never written to disk anymore. Only near-miss battle logs are kept, for debugging.
- The monitor no longer clears your clipboard when the game starts.
