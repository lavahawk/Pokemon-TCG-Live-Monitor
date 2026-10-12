---
tags: [log]
---
# Session Log
Append newest at the bottom. Format: date, who, what was done, what's next.

## 2026-10-11 — Claude (Phase 1: review)
**Did:**
- Read every Python module end to end (16.2k lines), all launchers/installers/Inno scripts, README/release notes and the auto-clicker handoff doc.
- Staged copies of the code, DB, logs and state files into a sandbox; ran import tests, a reproduction harness, a log/DB integrity audit, and rendered the dashboard offscreen with real data.
- Wrote this vault: architecture, process map, data model, 11 module notes, bug register (35 bugs), security review (11 items), data integrity audit.

**Confirmed by execution:** BUG-001, 004, 005, 007, 008, 023, 027; matplotlib/PySide6 compatibility OK. **Confirmed from data/logs:** BUG-002 (5 duplicate rows), 011, 014, 019, 020, 021, SEC-01 (code).

**Not touched:** no source file, DB or setting on the PC was modified. The only addition to the project folder is this `DevVault/`.

**Next:** get answers to [[00 Start Here#Open questions for Lva]] → start fix batch 1 ([[Bug Register#Suggested fix order]]). Back up `tcg_battles.db` before any data change.

## 2026-10-11 (later) — Claude (Phase 2: v2.4 fixes)
**Context / decisions from Lva:** auto-start (hidden, low CPU until the game runs) is the main mode and the installer must work; a terminal window is debug mode. Rank leagues = overlay thresholds. DB cleanup approved. Auto-export must work end to end. **No Claude co-author/attribution lines in commits.** Claude should do the git pushes.

**How the work was done:** the device shell (VM) failed to start, so code was edited in the cloud sandbox on copies and written back to the PC with file sync. Originals of every replaced file: `Backups/pre-v2.4-code/`. DB backup: `Backups/tcg_battles.backup_2026-10-11.db`.

**Data:** removed duplicate rows 5, 29, 34, 35, 36 and test row 11. Record is now 18-15.

**New modules**
- `game_window.py`: exact-title game window lookup, a cached handle, the foreground check and the DPI awareness setup. It replaces the 3 different window finders.
- `BattleEndAutomation.py`: the reworked auto-export state machine (see [[AutoClicker and ContinueBlocker]] and the handoff doc).
- `leagues.py`: ladder league thresholds and weights (overlay + analytics).
- `bootstrap_setup.ps1`: finds or installs Python 3.12, then runs `setup_install.py`. Used by every installer.
- `installer_common.iss`: shared Inno parts. `release_manifest.txt`: the single shipped-file list.

**Rewritten:** `TCGLiveMonitor.py` (pythonw-safe, idle loop, clipboard sequence number, DB-hash dedupe, worker thread for parse + OCR, `--ocr-test`), `BattleDatabase.py` (schema v2 migration, local time, `log_hash` UNIQUE, spike cleanup, resets survive rebuild, column whitelist), `AutoClicker.py` (multi-scale + ROI cache + ctypes clicks), `BattleState.py`, `setup_install.py`, installers/bats.
**Patched:** `AIParseBattleLog.py`, `StatsUI.py` (BUG-001 indent, tournament flag, URL allowlists, clipboard access removed, QThread lifetime, debug buttons, auto-export toggle, Japan columns, geometry debounce, sprite paths), `OverlayUI.py`, `RankDetector.py`, `ContinueBlocker.py`, `SetupAutoClicker.py`, `japan_data.py`, `deck_analytics.py`, `startup_utils.py`, `requirements.txt` (dropped xlwings/mouse; pyautogui not needed).

**Verified here (Linux sandbox, offscreen Qt, Windows APIs stubbed):**
- Simulated `pythonw` (stdin/stdout = None): old monitor → `AttributeError … isatty`; v2.4 starts, logs to `Logs/monitor.log`, idles.
- Monitor pipeline on a DB copy: an already-stored log is ignored (hash), a new log is saved + parsed (`BATTLE_ID` → post-battle update targets that id), the clipboard echo is ignored, ordinary copied text is never written to disk.
- DB migration on the real DB copy: timestamps converted (10:00Z → 05:00 EST, 01:20Z → 21:20 EDT), 33/33 hashes backfilled, spikes removed, idempotent, safe with 4 concurrent openers.
- Matcher: finds BATTLE LOG/export at window heights 720/900/1136/1440 (0.63–1.27× scale), no false positives on the battle screen; ~5–8 ms per poll after the first hit.
- Automation simulator (6 scenarios): auto export, user exported first (no clicks), game unfocused (no clicks), swallowed first click (re-click), export never lands (2 retries), lingering end screen + next battle (handled once each).
- Parser on all 48 real logs: winner/opponent correct for every one; local-mode crash gone.
- Release ZIP built from the manifest and every module imports from it. `bootstrap_setup.ps1` parses (pwsh 7.4). `test_rank_weighted.py`: 7/7 pass.
- Dashboard rendered with the migrated DB (local times, 33 games, 54.5%).

**Not verifiable here (needs the real PC):** live auto-start at login, real clicks in PTCGL, Tesseract OCR, Inno compile, pip install on Windows.

### Windows verification checklist
1. Close any running monitor/overlay (Task Manager → python/pythonw), then run `Install_Dependencies.bat` once (keeps your auto-start setting; reuses `.venv` if it's Python 3.10–3.12).
2. Debug run: `Run_TCGLiveMonitor_Command_Prompt.bat`. Expect "Monitor v2.4 starting … Waiting for Pokemon TCG Live…". The first start migrates the DB (one time).
3. Open PTCGL → overlay appears; play a game; at the end screen watch `Logs\autoclicker.log`: "BATTLE LOG button visible" → "Clicked BATTLE LOG" → "Clicked export" → "Auto-export complete". The dashboard shows the battle with local time.
4. If the BATTLE LOG button is never seen: run `.venv\Scripts\python.exe SetupAutoClicker.py` to recapture both templates (now works on any monitor).
5. Auto-start: `.venv\Scripts\python.exe AutoRun_Add.py`, sign out and back in, then check that `Logs\monitor.log` shows "(… headless)" and "Waiting…".
6. Installer: `Build_Inno_Installer.bat` (needs Inno Setup 6) → run Setup.exe on a test account.

### Git
GitHub isn't linked to this Claude account (`add_repo` → "link your GitHub account"), and the PC shell was unavailable, so **nothing is committed or pushed yet.** Either link GitHub in claude.ai Settings → Connectors so Claude can push, or run on the PC:
```
cd %USERPROFILE%\Downloads\BattleLogImport
git add -A
git commit -m "v2.4: fix auto-start, rework battle-end auto-export, installers, data integrity and Limitless fixes"
git push
```
(`DevVault/` is included; `Backups/` is gitignored.)


## 2026-10-12 — Claude (Phase 3: real-game verification + follow-ups)
**Did:** Verified auto-export in real matches and fixed what the game exposed (BUG-037 home-screen misclick, BUG-038 HUD detector, blocker timing → standby blocker 0.05 s, Master-league rank OCR). Dashboard performance (lazy deck pages, hidden-hub dashboard, background sprites, opacity slider). Statistics rework (exact Beta, pooling, meta-adjusted, tie modes, weighted personal records). Unified meta sheet (meta_sources.py: online + in-person + Japan, era/legality weighting). Preferences (weights.py). New Meta and In Person tabs, decklist capture (decklists.py). Published v2.4.0 as a GitHub pre-release.

**Next:** see [[Handoff 2026-10-12]] → Open items (silent-install exit, rebuild installer, manifest update).
