---
tags: [module]
file: BattleDatabase.py
lines: 597
---
# BattleDatabase.py: SQLite access layer

Schema and derived numbers are in [[Data Model]]. Each method opens its own `sqlite3.connect` and closes it; `init_database()` runs (and prints) on every construction. The overlay constructs it once; the parser and monitor construct it per call site.

| Method | Notes |
|---|---|
| `add_battle` | INSERT + `update_session_stats(result, rank)` (local date) |
| `update_session_stats` | Increments today's row (local `datetime.now().date()`) |
| `rebuild_session_stats` | DELETE + regroup by `DATE(timestamp)` (UTC), so dates shift (BUG-004) and wipe manual resets |
| `update_battle_record` | Dynamic `SET col=?` from keys (SEC-07) → rebuild |
| `delete_battle` | → rebuild |
| `reset_today_stats` | Zeroes today's W/L only |
| `get_current_rank` / `get_max_rank` | `rank_history` latest / MAX (BUG-020) |
| `get_all_time_stats` | `WHERE my_rank IS NOT NULL` (BUG-024) |
| `get_win_rate_over_time(days)` | `date('now','-N days')` UTC |
| `get_deck_*`, `get_all_battles_with_rank` | Feeds deck dashboards and [[deck_analytics]] |

Ideas: one connection helper with `timeout=10`, `PRAGMA journal_mode=WAL`; a `schema_version` table; an index on `battles(my_deck)`, `battles(timestamp)`; a `log_sha256 UNIQUE` column (BUG-002).
