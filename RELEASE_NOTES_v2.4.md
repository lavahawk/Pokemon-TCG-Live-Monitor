# Pokemon TCG Live Monitor v2.4

A reliability release. Every fix is tracked in `DevVault/03 Findings/Bug Register.md`.

## Install
Download **`PokemonTCGLiveMonitor-2.4.0-Setup.exe`** below and run it. That's all.

- **Everything is included.** The installer carries its own Python runtime with every package pre-installed, plus Tesseract OCR. Nothing is downloaded during setup, and any Python already on your PC is left alone.
- **No admin rights.** It installs for your Windows account only (`%LOCALAPPDATA%\Programs\Pokemon TCG Live Monitor`).
- **Upgrades keep your data.** Installing over v2.x keeps your battle history, settings and captured button images, and cleans up the old `.venv` and batch files. Uninstalling asks before deleting your battle history.
- Start menu: **Pokemon TCG Live Monitor** (background monitor), **Stats Dashboard**, and a Tools folder (debug console, recapture auto-export buttons, log files).
- Windows SmartScreen may say "Windows protected your PC" because the installer isn't code-signed. Click **More info → Run anyway**. You can check the file against the `.sha256` checksum attached to this release.
- Requires Windows 10 or 11, 64-bit.

## Auto-start
- **Auto-start works again.** Launching at Windows login (hidden, `pythonw`) crashed immediately because the monitor read the console input that `pythonw` doesn't have. It now runs fully in the background, writes its output to `Logs\monitor.log`, idles at low CPU priority until Pokemon TCG Live opens, and starts the overlay only once the game is running.
- Auto-start uses the registry Run key (the installer checkbox) instead of an elevated scheduled task. Old v2.x scheduled tasks are removed.

## Battle-end auto-export (reworked)
- **No more clicks on the wrong screen.** A button image is only acted on if OCR confirms it actually says "BATTLE LOG". Before, a look-alike near the PLAY button on the home screen could be clicked.
- **Reliable battle detection.** The in-battle check now looks for the in-game settings gear instead of sampling three pixel colours. The old check had stopped matching the game's layout.
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
