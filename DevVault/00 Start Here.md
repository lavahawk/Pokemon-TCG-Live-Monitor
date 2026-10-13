---
tags: [index, handoff]
updated: 2026-10-13
---
# PTCGL Monitor — Dev Vault (Start Here)

This vault is the shared engineering notebook for **Pokemon TCG Live Monitor** (`BattleLogImport/`). Anyone (human or AI) should be able to pick up from here. Open this folder in Obsidian as a vault (`Open folder as vault` → `DevVault`).

> [!info] Current phase
> **Phase 1: full code review and process mapping. DONE (2026-10-11).**
> **Phase 2: v2.4 fixes. CODE DONE (2026-10-11).** 33 bugs + 8 security items fixed and written to the project folder (originals in `Backups/pre-v2.4-code/`). See [[Session Log]].
> **Phase 3: real-game verification + v2.4 follow-ups. DONE (2026-10-12).** Auto-export, blocker, rank OCR verified in real matches; unified meta sheet, statistics rework, Meta / In Person tabs, preferences.
> **Phase 3b: dashboard + statistics overhaul. DONE (2026-10-12, afternoon).** Interactive charts, deck pin/star/ignore, hierarchical Bayesian Deck Score ([[deck_score]]), opponent-strength weighting, Meta tab data filters, hover formulas.
> **v2.5.0 released (2026-10-12):** installer rebuilt and install-tested, hidden monitor verified, pushed and published.
> **Phase 4: data sources + card usage. DONE (2026-10-13).** Whole-window online + City League data, decklist card usage, Meta → Cards, opponent deck from revealed cards, Japan tab on Limitless. → **[[Handoff 2026-10-13]]** (read this first), sources in [[Data Sources]].

## Map of this vault
| Area | Note | What's in it |
|---|---|---|
| Architecture | [[System Overview]] | Processes, components, data stores, external services |
| Architecture | [[Process Map]] | Step-by-step flows: startup, battle lifecycle, stats UI, Limitless tournament flow |
| Architecture | [[Data Model]] | SQLite schema + every dot-file / cache file and who reads/writes it |
| Modules | [[deck_score]] · [[TCGLiveMonitor]] · [[BattleEndAutomation]] · [[AIParseBattleLog]] · [[BattleDatabase]] · [[RankDetector and BattleState]] · [[OverlayUI]] · [[StatsUI]] · [[Limitless Dashboard Manager]] · [[deck_analytics]] · [[japan_data]] · [[AutoClicker and ContinueBlocker]] · [[Startup and Installers]] | One note per module: purpose, key functions, gotchas, linked bugs |
| Findings | [[Bug Register]] | Every bug with ID, severity, status, location, evidence |
| Findings | [[Security and Privacy Review]] | Vulnerabilities and privacy issues |
| Findings | [[Data Integrity Audit]] | What's actually wrong in `tcg_battles.db` and `Logs/` today |
| Dev | [[Dev Environment and Test Harness]] | How the code was run off-Windows, scripts in `04 Dev/scripts/` |
| Dev | [[Session Log]] | Dated log of every work session — **append to it** |
| Dev | [[Handoff 2026-10-13]] | Latest handoff (previous: [[Handoff 2026-10-12]]) |
| Architecture | [[Data Sources]] | Every meta data source: used, rejected (double counting), limits |

## Headline findings (details in [[Bug Register]])
1. **Limitless auto check-in and match-chat polling never start.** Part of `LimitlessDashboardManager.__init__` was accidentally indented into `_tournament_poll` (BUG-001). Reproduced.
2. **About 13% of battle records are duplicates.** 5 of the 39 rows are re-saves of an earlier log, which adds 4 phantom losses (BUG-002, see [[Data Integrity Audit]]).
3. **Release packaging is out of sync.** None of the 3 installers ship `japan_data.py`, `BattleState.py` or `ContinueBlocker.py`, so a fresh install's dashboard fails to import (BUG-003).
4. **Times are mixed UTC and local.** Session W/L reshuffles after any edit/delete, and UI times show 4–5 h ahead (BUG-004). Reproduced.
5. **The rank-weighted win rate does nothing.** It's calibrated for 1500–1900 Elo, but real ranks are 3–260, so every game gets the same 0.15 weight (BUG-007). Reproduced.
6. **Tournament tagging is dead end to end.** `is_tournament_battle()` is never called, and the `.in_tournament` flag is stale (BUG-008).
7. **Local-only mode crashes** with `UnboundLocalError` when you type the opponent's deck in a console (BUG-005). Reproduced.
8. **Privacy issue.** While the game runs, anything of 120+ characters that you copy and that isn't a battle log is saved to disk in `Logs/unmatched_*.txt` (SEC-01).

## How to resume
1. Read [[Session Log]] (last entry) → [[Bug Register]] (status column).
2. Pick the next item from [[Bug Register#Suggested fix order]]. Mark it `in-progress` in the register.
3. Reproduce first with the harness in [[Dev Environment and Test Harness]], then fix, then re-run.
4. Append a dated entry to [[Session Log]] and flip the bug's status.

## Decisions (answered 2026-10-11)
- [x] Vault stays in `BattleLogImport/DevVault/`.
- [x] Normal use: auto-start at login, hidden, low CPU until the "Pokemon TCG Live" process appears. Debug: terminal window. The **installer version must work**. Both were fixed in v2.4 (BUG-009, BUG-003, BUG-036).
- [x] Rank leagues = the overlay's thresholds (30/110/230/390/550). They now live in `leagues.py` and are used by the overlay and the analytics.
- [x] DB cleanup approved and done (rows 5, 11, 29, 34, 35, 36 removed; backup in `Backups/`).
- [x] Public GitHub repo is behind. **Lva wants commits/pushes done by Claude, with no Claude co-author/attribution lines in commits.** GitHub isn't linked to Claude yet (see Session Log).
- [x] Auto-export: rework so it works end to end. Rule: "a battle log on the clipboard means exported, by the user or by us".

## Still open
- [ ] Link GitHub (claude.ai → Settings → Connectors → GitHub, with access to `lavahawk/Pokemon-TCG-Live-Monitor`) so pushes can be made from here, or push from the PC (commands in Session Log).
- [ ] SEC-02: move the API key into Windows Credential Manager (needs a `keyring` dependency; deferred).
- [ ] BUG-033: Playwright replay fallback; BUG-028 remainder (lazy-load the web tabs).
