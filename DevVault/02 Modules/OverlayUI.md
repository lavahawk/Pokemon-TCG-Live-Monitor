---
tags: [module]
file: OverlayUI.py
lines: 968
---
# OverlayUI.py: in-game mini HUD

**Role:** a separate pythonw process (PySide6). A frameless, topmost "Elo:x | Max:y | W-L" pill with a league Pokéball, pinned 12 px inside the game window's bottom-right. Hosts the [[Limitless Dashboard Manager]] (imported from StatsUI) and opens the [[StatsUI]] window in-process.

- `MinimalOverlay` timers: position 1 s, stats 3 s, monitor-alive 5 s.
- `_is_valid_game_window`: exact title "pokemon tcg live", not a console, not owned by our scripts (better than RankDetector's matcher; reuse it there).
- League thresholds `get_league_from_elo`: ≥550 master, ≥390 ultra, ≥230 great, ≥110 poke, ≥30 quick, else nest. These match the real rank scale (3–260); [[deck_analytics]] does not (BUG-007).
- `LimitlessChatWindow`: click-through (WS_EX_TRANSPARENT), fades by age (25 s + 10 s) and by position; own messages right-aligned.
- Double-click the stats → reset today's W/L popup. ▲ → open/close the dashboard.
- `_dbg()` appends to `.overlay_debug.log` every second (BUG-019).
- Quits when the `.monitor_pid` process is gone (`pid_exists`, BUG-032).

Dead code: `calculate_session_stats` (Excel-based). The README still calls it click-through.
Related: BUG-019, 020, 032.

## Opponent deck card (2026-10-12)
`deck_popup.DeckConfirmPopup`, polled by `MinimalOverlay._poll_deck_confirm` every 1 s (`deck_timer`). Sits right-aligned 6 px above the mini GUI; the Limitless chat stacks above it while it shows. Requests come from [[AIParseBattleLog]] through `deck_confirm.py` (`Logs/.deck_confirm.json`), the fade signal from the monitor (`Logs/.menu_seen`).
- **show** (AI pick): "OPPONENT DECK · WIN", deck name, AI chip, blue accent. Click → edit. Fades 2.5 s after the menu is seen (at least 4 s on screen, 90 s fallback, hover pauses).
- **edit**: line edit + `QCompleter` (contains, case-insensitive) over your recorded opponent decks (most played first) then Limitless archetypes, plus Other. Shown straight away (amber, "WHAT DID YOU PLAY AGAINST?") when there's no AI pick: local-only, no key, AI failed or blank. Known names snap to their spelling (`canonical_name`).
- **new**: unknown name → "Add new deck" / "Save as Other" / Back.
- **done**: `update_battle_record(opponent_deck, deck_source="Manual", confidence=100)`, synthesized two-note chime (`deck_confirm.chime_wav`, winsound SND_MEMORY in a thread), green check that draws in with an expanding ring, then fades.
- Shown with `WA_ShowWithoutActivating` so it never steals focus from the game; clicking it activates it for typing. ✕ keeps the current deck. A handled request is flagged in the file, so restarts don't re-show it; requests older than 15 min are ignored.

## New-session reset prompt, max Elo toggle (2026-10-12)
- The monitor writes `Logs/.game_session` when it detects the game. `_poll_game_session` (on the 1 s deck timer) waits until the overlay is visible, then shows the same Reset? popup as a double-click, with a "New session" caption. It fades in, stays 10 s (hover keeps it; leaving restarts 3.5 s) and fades out (`FadingPopup`, also used for the manual popup, which doesn't linger). Skipped when today's W-L is 0-0, when it's more than 120 s after game start, or when `overlay_session_reset_prompt` is off. A monitor restart counts as a new session.
- `overlay_show_max_elo` off → "Elo:1487 | 4-2". `adjustSize` is deferred with `QTimer.singleShot(0)`: called straight after `setText` the layout still had the old size hint and the pill didn't shrink.
- Both are toggled from Advanced → **Preferences · Overlay** (StatsUI) and re-read every 3 s, no restart needed.
- **Gotcha:** the overlay is shown before its first `follow_game_window` tick, so anything anchored to it must wait for `_overlay_placed` (set right after the first `SetWindowPos`). The Reset? popup is re-anchored each move (`_position_reset_popup`).

## 2026-10-13
- Today's W-L skips games with decks marked **Ignore** on the dashboard (`ignored_decks()` reads `.deck_flags.json`; `BattleDatabase.get_today_stats(ignored_decks)` subtracts their wins/losses since the last reset).
