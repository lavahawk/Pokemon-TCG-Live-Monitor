---
tags: [module]
file: AIParseBattleLog.py
lines: 635
---
# AIParseBattleLog.py: per-battle interpreter

**Role:** run once per log (`python AIParseBattleLog.py <log path>`). Works out my deck, opponent deck, result and confidence, then writes Excel + DB. It can also be run by hand from the Settings tab (falls back to the clipboard, then the newest log).

## Flow (`main`, L549–631)
1. `ensure_username()`; read the log (arg → clipboard → latest log).
2. AI mode if a key exists and local-only is off: `ai_parse()` tries `gpt-5.4-nano-2026-03-17` → `gpt-4.1-mini` → `gpt-4o` with `response_format=json_object`; the prompt includes the top-50 Limitless deck names from `.meta_cache_limitless_standard.json` (fallback: Excel "Limitless Meta" col B). Tolerant JSON coercion (`_flatten_scalar`, `_coerce_*`).
3. Local mode: `local_fallback_parse()`: `.last_deck`, a console prompt (only with a TTY), otherwise the opponent's first Pokémon played to the Active Spot (BUG-005 crash path).
4. **The log beats the AI for the result:** `parse_result_from_log` (last `X wins.`) overrides and bumps confidence to ≥90/95.
5. **OCR beats the AI for my deck:** `.last_deck` replaces `My_deck`.
6. `save_to_excel` (sheet per deck, BUG-030) and `save_to_database` (attaches `.chat_capture.json`; `is_tournament` never passed, BUG-008).

## Notes
- A module-level `db = BattleDatabase()` runs at import (creates the DB if missing).
- `is_tournament_battle` + `parse_opponent_from_log` are complete but unused.
- `parse_winner_from_log` regex limits names to `[A-Za-z0-9_-]` (BUG-023).
- No OpenAI timeout (BUG-031). The prompt includes the full log (prompt-injection surface is small, since output only lands in the DB).

Related: BUG-005, 008, 023, 030, 031, SEC-09.
