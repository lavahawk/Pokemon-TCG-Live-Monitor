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
