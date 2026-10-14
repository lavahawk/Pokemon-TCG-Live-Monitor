---
updated: 2026-10-14
---
# PTCGL Monitor — Start Here

The only note to read on resume. Open other notes **only when the task touches them**. `99 Archive/` is history (old handoffs, session logs, fixed bugs, the security review). Don't read it unless you're digging into why something is the way it is.

## What it is
A Windows app that watches Pokémon TCG Live. Battle log → SQLite (`tcg_battles.db`) → in-game HUD (`OverlayUI.py`) + dashboard (`StatsUI.py`, ~10k lines; grep, don't read).
`TCGLiveMonitor.py` (monitor loop) runs `AIParseBattleLog.py` once per battle. `BattleEndAutomation.py` + `AutoClicker.py` export the log automatically. Settings live in `.app_settings.json` (`app_settings.py`; StatsUI `_save_app_setting`).
Repo `lavahawk/Pokemon-TCG-Live-Monitor`, branch `main`. Commits have **no Claude attribution lines**. Latest release: v2.5.0.

## Rules of the road
- Python: `.venv\Scripts\python.exe`. Tests: `test_card_usage.py`, `test_rank_weighted.py`.
- Offscreen UI check: `QT_QPA_PLATFORM=offscreen`, build the widget, `grab().save(png)`. Work on a **copy** of the DB: importing `AIParseBattleLog` creates or migrates `tcg_battles.db`.
- The overlay imports `StatsUI` once: after UI changes, restart the overlay.
- Limitless API: only via `meta_sources._api_get` (50 req / 5 min without a key).
- Old battle logs are cp1252: read them with `read_battlelog_file`.
- Bash heredocs containing `'` sometimes fail. Write patch scripts to the scratchpad instead (keep CRLF).
- Release: bump `version.py`, add `RELEASE_NOTES_vX.md` to `release_manifest.txt`, run `installer\build_installer.ps1`, install-test, tag, `gh release create`.

## Map (open on demand)
- Architecture: [[System Overview]] · [[Process Map]] · [[Data Model]] · [[Data Sources]]
- Modules: [[AIParseBattleLog]] · [[deck_score]] · [[StatsUI]] · [[OverlayUI]] · [[TCGLiveMonitor]] · [[BattleDatabase]] · [[BattleEndAutomation]] · [[AutoClicker and ContinueBlocker]] · [[RankDetector and BattleState]] · [[Limitless Dashboard Manager]] · [[deck_analytics]] · [[Startup and Installers]]

## State
See **Session log** below.

## Open
- [ ] Release v2.6 (the 10-13 and 10-14 work isn't in an installer yet).
- [ ] 9 stored opponent labels contradicted by the opponent's cards (#4, 12, 17, 27, 32, 44, 48, 52, 56). Relabel only with the user's OK, after a DB backup.
- [ ] BUG-033: the Playwright replay fallback fails silently. SEC-02: the API key is in plaintext. SEC-09: no disclosure of third-party data sharing.
- [ ] Ideas: rank chart per deck; tune `CLOSE_CALL` / `CLOSE_CONTENDER` once there are more confirmed labels; auto-capture a decklist when all 60 cards have been seen.

## Session log (newest first, one line each; prune past ~10 to the archive)
