---
tags: [architecture, data]
updated: 2026-10-11
---
# Data Model

All paths are relative to `BASE_DIR` (the folder containing the scripts). There is no separate user-data directory (see BUG-003).

## SQLite: `tcg_battles.db` ([[BattleDatabase]])
```sql
battles(
  id INTEGER PK AUTOINCREMENT,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,   -- UTC! (BUG-004)
  my_deck TEXT NOT NULL,          -- AI guess, overridden by OCR .last_deck, then again by post-battle OCR UPDATE
  opponent_deck TEXT NOT NULL,    -- AI guess / manual / first Active Pokémon (local mode)
  result TEXT NOT NULL,           -- 'Win' | 'Loss' | 'Tie' (from log "X wins." when parsable)
  my_rank INTEGER,                -- parser writes pre-battle .last_rank; monitor overwrites with post-battle OCR rank
  confidence INTEGER,             -- 0-100
  deck_source TEXT,               -- 'AI' | 'Local' | 'OCR' (legacy) | 'Manual'
  log_file TEXT,                  -- absolute path (older rows: '\Logs\...' or relative)
  is_tournament INTEGER DEFAULT 0,-- never set (BUG-008)
  chat_log TEXT                   -- JSON {round, opponent, messages[]} from .chat_capture.json
)
rank_history(id PK, timestamp UTC, rank INTEGER NOT NULL, deck_name TEXT)   -- one row per OCR read (noisy)
session_stats(id PK, date DATE UNIQUE, wins, losses, max_rank, min_rank)     -- denormalized; local date on insert, UTC date on rebuild
```
Migrations: ad-hoc `ALTER TABLE ADD COLUMN` for `is_tournament`, `chat_log` in `init_database()`. No schema version and no indexes besides PKs. Every call opens and closes its own connection (no context managers, no WAL); 4 processes share it.

Derived numbers:
- Overlay "Elo" = latest `rank_history.rank`; "Max" = `MAX(rank_history.rank)`; W-L = today's `session_stats`.
- Dashboard totals = `get_all_time_stats()` (filters `my_rank IS NOT NULL`, BUG-024).
- Deck analytics = `GROUP BY my_deck` (exact string, so OCR typos make new decks).

## Shared state files
| File | Writer | Reader | Content / notes |
|---|---|---|---|
| `.user_config` | monitor / parser (first-run prompt) | all | TCG Live username |
| `.openai_key` | installer bat, Settings tab | parser, Japan | plaintext key (SEC-02) |
| `.app_settings.json` | Settings tab | parser, monitor | `{local_only_mode}` |
| `.monitor_pid` | monitor | overlay (liveness), StatsUI (console toggle, close app) | PID |
| `.monitor_lock` | monitor | monitor | msvcrt byte-lock + PID |
| `.last_deck` / `.last_rank` | monitor OCR | parser | latest OCR deck name / rank |
| `.max_rank` | `Fix_MaxRank.py` | overlay (fallback only) | effectively unused (BUG-020) |
| `.in_tournament` | Limitless manager | parser (`is_tournament_battle`, never called) | `{in_tournament, opponent}`; stale |
| `.chat_capture.json` | Limitless manager | parser → `battles.chat_log` | current match chat |
| `.limitless_dashboard_state.json` | Limitless manager | Limitless manager | `{background_enabled, auto_checkin_enabled}` |
| `.limitless_web_profile/` | QtWebEngine | QtWebEngine | **Limitless login cookies** |
| `.ptcgl_replay_profile/` | (legacy) | – | current code uses an off-the-record profile |
| `.meta_cache_{limitless_standard,limitless_pocket,trainerhill,japan}.json` | MetaFetcher / japan_data | StatsUI, parser (deck list for AI prompt), japan_data | 1 h TTL |
| `.japan_translation_cache.json` | japan_data | japan_data | AI translations |
| `.meta_icon_cache/*.png` | sprite fetcher | StatsUI | pokesprite / PokeAPI images |
| `.deck_icon_overrides.json`, `.pinned_decks.json` | StatsUI | StatsUI | per-deck UI prefs |
| `.stats_window_geometry.json` | StatsUI | StatsUI | written on every move/resize pixel |
| `.console_pref` | StatsUI | StatsUI | `visible`/`hidden` |
| `.overlay_debug.log` | OverlayUI | humans | unbounded (BUG-019) |
| `Logs/battle_log_<local ts>.txt` | monitor | parser, replay, StatsUI | cp1252 (BUG-011) |
| `Logs/unmatched_<ts>.txt` | monitor | humans | arbitrary clipboard (SEC-01) |
| `Logs/autoclicker.log`, `Logs/blocker_debug.log`, `Logs/.blocker_dismiss` | monitor / blocker | humans / blocker | |
| `TCGExampleSheet.xlsx` | parser | parser (deck list fallback, sheet "Limitless Meta") | one sheet per my_deck, col A result, col B opp deck |
| `screen_regions.json` | (manual) | RankDetector | percent-based OCR regions: `rank`, `my_deck_name`, `menu_text` |
| `button_templates/*.png` | SetupAutoClicker | AutoClicker | pixel templates (resolution-specific) |

## Battle log text format (what the parsers rely on)
- Starts with `Setup`; turns are `<name>'s Turn` lines (new format) or `Turn # N - <name>'s Turn` (old).
- Ends with one of: `All Prize cards taken. X wins.` · `Opponent conceded. X wins.` · `You conceded. X wins.` · `Opponent took all of their Prize cards. X wins.` · `Knocked Out with no Benched Pokémon. X wins.` · `Opponent was inactive for too long. X wins.`
- `parse_winner_from_log` takes the last `[A-Za-z0-9_-]+ wins.` match (BUG-023 for other name chars).
