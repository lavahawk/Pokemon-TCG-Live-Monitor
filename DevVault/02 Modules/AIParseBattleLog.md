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

## Deck card handoff (2026-10-12)
- After saving, `main` calls `deck_confirm.write_request(battle_id, deck, source, needs_input)`: source `ai` (card shows the pick) or `guess` / `none` (card asks).
- The local-mode console prompt for the opponent deck is gone. Under the monitor stdout is captured, so that prompt was invisible and the parser sat until the 180 s timeout. The monitor now sets `PTCGL_NO_PROMPT=1`, so `_console_available()` is False for the remaining my-deck / result prompts too.
- `deck_source` stored as AI only when the AI parse actually succeeded (it used to say AI whenever a key existed, even after falling back).


## Opponent deck from revealed cards (2026-10-13)
- `card_evidence(log, username)`: `card_usage.log_cards` collects the cards the **opponent** revealed (lines they start, `- opp …` sub-lines, the `•` lists under them; text after the user's name is cut so attack targets don't count; damage breakdowns are skipped). `card_usage.classify` ranks meta archetypes by log P(share) + Σ log P(card in that archetype's lists) from the sheet's `cards` (floor 0.4% for a Pokémon the archetype never plays).
- **AI mode:** the prompt gets the opponent's revealed Pokémon, the card-based top 3 and "the user's own cards are not evidence". **Cross-check:** if the AI's name has Pokémon the opponent never showed and the card pick (≥ 85%, `CARD_PICK_MIN`) fits the revealed Pokémon, the card pick is stored (`deck_source` "Cards", overlay chip CARDS).
- **Local mode:** the card pick replaces "first Pokémon to the Active Spot": ≥ 85% → CARDS (shown), 50–85% → GUESS (prefilled, asks), else the old guess.
- Measured on the 54 stored battles with logs: the cross-check would change 9 labels, and all 9 were wrong AI labels (e.g. #48 "Gengar" = the user's own deck vs N's Zoroark ex / Zorua / Reshiram; #52 "Dragapult" vs Mega Sharpedo ex / Toxtricity; #17 "Dragapult Dusknoir" vs Blaziken ex / Combusken). Known limits: hybrids (Dragapult + Mega Starmie), Japan-only decks with no English lists, games from rotated formats.
- Needs the meta sheet with card data (built by Meta → ↻ Refresh); without it nothing changes. Old logs may be cp1252: always read them with `read_battlelog_file`.
