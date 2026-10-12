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
