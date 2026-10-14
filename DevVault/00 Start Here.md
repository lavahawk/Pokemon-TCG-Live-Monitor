---
updated: 2026-10-14
---
# PTCGL Monitor — Start Here

The only note to read on resume. Open other notes **only when the task touches them**. `99 Archive/` is history (old handoffs, session logs, fixed bugs, the security review). Don't read it unless you're digging into why something is the way it is.

## What it is
A Windows app that watches Pokémon TCG Live. Battle log → SQLite (`tcg_battles.db`) → in-game HUD (`OverlayUI.py`) + dashboard (`StatsUI.py`, ~10k lines; grep, don't read).
`TCGLiveMonitor.py` (monitor loop) runs `AIParseBattleLog.py` once per battle. `BattleEndAutomation.py` + `AutoClicker.py` export the log automatically. Settings live in `.app_settings.json` (`app_settings.py`; StatsUI `_save_app_setting`).
Repo `lavahawk/Pokemon-TCG-Live-Monitor`, branch `main`. Commits have **no Claude attribution lines**. Latest release: v2.6.0.

## Rules of the road
- Python: `.venv\Scripts\python.exe`. Tests: `run_tests.py` runs every `test_*.py` (parser, database, decklists, pet state, card usage, rank weights; all isolated from the real DB/settings, no network).
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
- [x] v2.6.0 released 2026-10-14 (installer smoke-tested in the build; not yet install-tested on the PC).
- [ ] 9 stored opponent labels contradicted by the opponent's cards (#4, 12, 17, 27, 32, 44, 48, 52, 56). Relabel only with the user's OK, after a DB backup.
- [ ] Ideas: tune `CLOSE_CALL` / `CLOSE_CONTENDER` once there are more confirmed labels.

## Session log (newest first, one line each; prune past ~10 to the archive)
- **2026-10-14 (post-2.6.0):** BUG-033 fixed: the dead Playwright helper subprocess is gone; without Playwright the replay opens in the default browser and Explorer selects the log to drag in (`_open_replay_manually`). `test_rank_weighted.py` now pins default weights and tie mode, so the user's settings no longer fail it. SEC-02 fixed: the OpenAI key is DPAPI-encrypted in `.openai_key.dpapi` (`app_settings`); a plaintext `.openai_key` (older versions, the installer) is migrated and deleted on first read. SEC-09 fixed: privacy notice in Settings → AI Parsing Mode; `ai_anonymize_names` (default on) sends logs to OpenAI as Player / Opponent (`anonymize_battlelog`, `log_player_names`). Deck page: RANK WITH THIS DECK card (`_create_deck_rank_card`, chart code at the end of `charts.py`; hidden with 0 ranked games, a note with 1). BUG-034 done: pyflakes is clean on all top-level modules (keep it that way); dead helpers removed outside StatsUI; StatsUI reconfigures stdout to UTF-8 (a cp1252 pipe crashed on ✓). Unreferenced StatsUI candidates left in place: `ClickableFrame`, `_post_json`, `_create_metric_grid`, `_create_scale_metric_card`, `_create_interval_metric_card`, `_summarize_meta_record`, `_probability_accent`, `_create_top_meta_table`, `_create_matchup_table`, `_trend_display`, `_meta_header_bar`, `_uncertain_note`, `enable_limitless_background_watch`; unused BattleDatabase `get_deck_stats`, `get_win_rate_over_time`, `get_deck_battle_history`, `get_all_battles_with_rank`. Parser fixes from the new tests: winner must be a whole name ("MrAsh"/"Mr. Ash" ≠ "Ash"); numbered turn headers no longer yield "Turn # 1 - X" as a name; local deck guess anchored to line start and accepts accents. Pet state tolerates non-object JSON and string bools and saves atomically; decklists tolerate `{"lists": null}`. Decklist auto-capture (`decklists.auto_capture`, called in `AIParseBattleLog.main()` after the deck card): `card_usage.log_deck_counts` counts max simultaneous copies (not plays), `merge_seen` merges games newest first, stops on >60 or a 2nd ACE SPEC, needs `CONFIRM_GAMES`=3 extra games adding nothing; saves "<deck> (auto)", never over a user list; unlinking an auto list blocks it. `ACE_SPECS` is hand-maintained. Re-reads all the deck's logs per battle (seconds at ~30 games). On the DB today nothing qualifies (Gengar Testing 60/60 but unconfirmed + has an export).
- **2026-10-14:** vault slimmed (this note + archive). Shipped:
  - import sounds (`sounds.py`, Advanced → Preferences · Sound)
  - auto-export clicks pinned with `ClipCursor` (`AutoClicker.physical_click`)
  - DB editor: one actions cell, auto-refresh, no Refresh button
  - parser returns top-3 `Candidates`, and confidence is now the **opponent-deck certainty** (no result bump). The overlay card shows the 3 choices with icons; under 50% it asks and waits.
  - deck page: Last-10 squares jump to the game; per-game Replay / Cards played / Deck archetype buttons
  - Snapshot **Decklist** button: import/link a list (`decklists.link_decklist`), card suggestions, Meta → Cards, TrainerHill
  - optional **HUD buddy** (`pet.py`, `pet_sprites/`, CC BY-NC). All of it is unverified on a live game: restart the overlay, then check a battle import (sound, deck card) and the auto-export clicks while moving the mouse.
- **2026-10-14 (later):** `adblock.py` + `adblock_hosts.txt` (131 domains, editable): a `QWebEngineUrlRequestInterceptor` on every web profile (Limitless, Replay, TrainerHill, default). First-party hosts are never blocked; no cosmetic filtering. Setting `browser_adblock` (default on), toggled in Advanced → Preferences · Overlay. limitlesstcg.com home: 9 requests blocked.
- **2026-10-14 (evening):** Meta tab decluttered: no legend line or ⚖; the status line is short with details on hover; the source legend is on the Sources heading; the weights note appears only on weighted headings while custom weights are on; cell hovers are short (`_score_brief`; the full `_score_tooltip` stays on the deck page); the Cards summary is compact. The decklist dialog watches the clipboard (`QClipboard.dataChanged`) and lists your exports; the decklist menu has section headers.
- **2026-10-14 (night):** deck page: META SCORE and SCORE · YOUR GAMES (now shown ±) open Meta → Archetypes on your ★ row (`_show_deck_in_meta`, shown even when not starred via `_meta_focus_deck`), and META FACED scrolls to Matchups (`FlashOverlay` pulse). HUD buddy v2 (`pet.py`):
  - 1.5× size, kept crisp at any DPR
  - no shadow: feet touch the game window bottom and the top of the mini GUI (the overlay passes `drop` = 12 px / DPR and the ball position)
  - per-species walk speed
  - hops onto the HUD, peeks from below, goes into the Pokéball
  - wakes on hover; right-click feeds it
  - petting: double hop, hearts, faces that cycle
  - shiny 1/50 (`pet_sprites/<sp>/shiny/`) with sparkles
  - win: celebrates; loss: sad face, walks to the corner and naps (`react()`, called from `_poll_deck_confirm`)
- **2026-10-14 (late night):** buddy v3:
  - stands slightly *on* the mini GUI (+2 px)
  - peeks only clear of the mini GUI
  - into the ball rarer (2%): turns white, accelerates along a curve into it; release arcs out
  - battle start (`deck_confirm.mark_battle_started` from BattleEndAutomation → overlay → `pet.battle_start`): a cheer, then it slowly walks into the ball or naps right of the mini GUI until the result
  - hidden meters in `.pet_state.json`: hunger in games, happiness, energy, level. Hearts by mood; angry fit when starving; more naps when hungry or tired.
  - face bubbles on 1 in 5 clicks, only when fed
  - treats (`TREATS`): Oran / Pecha / Cheri / Chesto / Sitrus with effects; Rare Candy 1/20 (level up, meters maxed, 30 min cooldown)
- Double-clicking the mini GUI Pokéball recalls / sends out the buddy (`pet.toggle_ball`). A recalled buddy stays in through battles (`recalled`).
- Buddy v4:
  - off until the overlay Pokéball is double-clicked (`_on_ball_double_click` sets `overlay_pet`; Advanced only picks the species); recall persists (`recalled` in `.pet_state.json`)
  - after a battle it stays in the ball until `menu_seen` (60 s fallback)
  - faint thought puff: berry when hungry, heart when untouched 10 min
  - Hop emote weight 0.25; ~75% of naps (and post-loss mopes) at `_nap_spot()` beside the mini GUI
