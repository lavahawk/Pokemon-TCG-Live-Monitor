---
tags: [findings, data]
updated: 2026-10-11
---
# Data Integrity Audit (snapshot 2026-10-11)

Source: copy of `tcg_battles.db` (39 battles, 115 rank_history rows, 8 session_stats rows) and all 48 `Logs/battle_log_*.txt`. Script: `04 Dev/scripts/log_audit.py`. Nothing on Lva's machine was modified.

## 1. Duplicate battles (BUG-002)
Logs were grouped by SHA-256 of their content:

| Content group | Log files (local time) | DB rows | Verdict |
|---|---|---|---|
| A | 2026-09-08 21:58:34, 22:05:55 | #28 Loss, #29 Loss | #29 duplicate |
| B | 2026-09-09 00:33:09, 01:55:44, 02:17:20, 02:22:29 | #33, #34, #35, #36 (all Loss) | #34–#36 duplicates |
| C | 2025-12-26 03:15:19 | #4 Win, #5 Win (same file path) | #5 duplicate/misattributed |
| D | 2026-08-16 22:06:51, 22:06:52 | #19 only | 2 files 1 s apart (2 monitor instances?); only one row |
| E | 2025-12-21 04:38 / 05:40, 09:14 / 09:33; 2025-12-21 05:00 / 2026-04-21 09:01; 2025-12-26 12:50 / 13:30 | one or none | duplicate files only |

**Impact:** 4 phantom losses + 1 phantom win. The real all-time record is **18-16** (52.9%) rather than 19-20 (48.7%). "Pult Hammers NAIC 2026" is **10-10** rather than 10-14. (If test row #11 is also removed: 18-15.)
> [!success] Cleaned 2026-10-11 (approved): rows #5, #29, #34, #35, #36 and test row #11 deleted. Record is now **18-15 (33 games)**. Backup: `Backups/tcg_battles.backup_2026-10-11.db`. On first start, v2.4 migrates the DB (schema v2): UTC→local timestamps, log hashes backfilled (all 33 rows), OCR rank spikes removed (3 and 4), session stats rebuilt.

## 2. Test data in production DB
Row #11 (`Dragapult Dusknoir` vs `Zygarde`, Loss, 2026-04-26) points to `Downloads\BattleLogImport\TestBattle.txt`, the bundled test log. It should probably be removed.

## 3. Timestamps are UTC (BUG-004)
Example: row #1 `2025-12-21 10:00:43` ↔ its log `battle_log_2025-12-21_05-00-37.txt` (EST, UTC−5). Every row is UTC. `session_stats` currently holds local-date numbers, but one call to `rebuild_session_stats()` (any edit/delete in the dashboard) rewrites them by UTC date (repro shows 09-09 becoming 3-10).

## 4. Rank history noise (BUG-020/021)
- Implausible ranks surrounded by stable values: id 24 = **3** (between 151s), id 54 = **4** (between 30s), id 41 = 20. They show up as dips in the Elo chart.
- OCR deck-name garbage in `rank_history.deck_name`: "Oragapult 2024 turbo", "Oragaputt 2026 smb3nk3", "VidQGd Pull CU CO SMDANKS", "Dragapult 2026 turba". None leaked into `battles.my_deck` in this snapshot, but the monitor's post-battle UPDATE copies the OCR deck into the latest battle, so it can.
- Real ranks: min 3, max 260. That's the scale BUG-007 must be calibrated to.

## 5. Encoding
Saved logs contain cp1252 bytes (`Pok\xe9mon`), so UTF-8 readers see "Pok�mon" (BUG-011).

## 6. Confidence anomalies
Row #30 has `confidence=0` for a Win whose log clearly ends "All Prize cards taken. 22lava44 wins." With the current code this can't happen (a log-confirmed result forces ≥90), so it was probably a manual edit or older code. Harmless.

## 7. Tournament flag
`.in_tournament` = `{"in_tournament": true, "opponent": ""}` (stale, BUG-017). `battles.is_tournament` is 0 for all rows (BUG-008). Rows #44–#45 do have `chat_log` captured (481 bytes each), so chat capture worked at least once (likely from the visible dashboard view).

## 8. Missed battle
`autoclicker.log` 2026-09-13 22:26:52 → the sequence fired, the export was not found, no log was saved, so there is no DB row. At least one game was lost (BUG-014).
