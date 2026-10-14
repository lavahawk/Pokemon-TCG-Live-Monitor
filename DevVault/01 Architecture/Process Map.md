---
tags: [architecture, process]
updated: 2026-10-11
---
# Process Map

## 1. Startup
```mermaid
sequenceDiagram
    participant U as User/Login
    participant M as TCGLiveMonitor
    participant O as OverlayUI
    participant G as PTCGL
    U->>M: launch (console / pythonw --headless / Run key)
    Note over M: IMPORT TIME: clear screen, banner,<br/>load/ask username (Tk dialog if no TTY)<br/>⚠ BUG-009: sys.stdin None under pythonw
    M->>M: argparse (--headless, --no-overlay)
    M->>M: _acquire_single_instance (msvcrt lock)
    M->>O: Popen pythonw OverlayUI.py
    O->>O: get_limitless_dashboard_manager() (⚠ BUG-001: no profile/timers)
    M->>M: start_battle_state_watcher() thread
    M->>G: wait_for_game_startup() poll process list every 10 s
    M->>M: pyperclip.copy('') ⚠ wipes user clipboard
    M->>M: detect_initial_stats(): OCR main menu ≤60 s → .last_deck/.last_rank + rank_history row
    M->>M: monitor_clipboard() forever
```

## 2. Battle lifecycle (the core loop)
```mermaid
flowchart TD
    A[Battle in progress] -->|watcher: HUD 2/3 anchors| B[was_in_battle]
    B -->|HUD gone 3x| C[battle_seen=True]
    C -->|BATTLE LOG template visible| D[launch ContinueBlocker<br/>run_battle_end_autoclicks]
    D --> E[click BATTLE LOG → launch 2nd blocker ⚠<br/>click export, retry ≤3]
    E -->|game copies log to clipboard| F
    U2[User clicks export manually] --> F
    F[Clipboard loop: is_battle_log?] -->|same hash < 600 s| X[skip as echo]
    F -->|new| G[save Logs/battle_log_TS.txt ⚠ cp1252]
    G --> H[signal blocker dismiss]
    H --> I[run_battle_end_autoclicks AGAIN<br/>⚠ cooldown 30 s; if watcher didn't run it,<br/>re-opens BATTLE LOG popup after export]
    I --> J[play ding — blocks]
    J --> K[subprocess AIParseBattleLog log_path ≤180 s — blocks]
    K --> K1{local-only or no key?}
    K1 -->|AI| K2[OpenAI 3-model fallback → JSON]
    K1 -->|local| K3[.last_deck + infer opponent's first Active<br/>⚠ BUG-005 crash if console prompt used]
    K2 --> L[result overridden by 'X wins.' line in log]
    K3 --> L
    L --> L2[my_deck overridden by .last_deck OCR]
    L2 --> N[Excel row + DB add_battle my_rank=.last_rank<br/>is_tournament always 0 ⚠ BUG-008]
    N --> O[wait_for_main_menu_and_detect ≤120 s — blocks]
    O --> P[OCR deck+rank → rank_history row<br/>UPDATE battles WHERE id=MAX id ⚠ BUG-006]
    P --> F
```
Key timing fact: the clipboard loop is **single-threaded**. From the moment a log is detected until the main-menu OCR finishes, up to about 5 minutes, no other clipboard content is examined (BUG-018).

Observed in `Logs/autoclicker.log`: in most battles the sequence runs *after* the log already arrived (user exported by hand). The export button then is "not found within 20s", and on 2026-09-13 22:26 the watcher fired, both blockers showed, the export never happened, and that battle is **missing** from the DB.

## 3. Overlay refresh
- Every 1 s `follow_game_window()`: find the window titled exactly "pokemon tcg live", pin the HUD bottom-right, write a debug line to `.overlay_debug.log` (unbounded, BUG-019).
- Every 3 s `load_stats()`: `rank_history` latest → Elo, `MAX(rank)` → Max, `session_stats` today → W-L.
- Every 5 s: is the `.monitor_pid` process alive? If not → quit.
- Double-click stats → reset today's W/L (lost on the next edit/delete because of `rebuild_session_stats`).
- ▲ → opens StatsWindow (created fresh each time; `WA_DeleteOnClose`).

## 4. Stats dashboard open
`StatsWindow.__init__` → builds 10 tabs eagerly, including **3 QWebEngineViews that start loading immediately** (Limitless dashboard, ptcglreplay, pokedata) → `load_stats()` → in 1.2 s, a MetaFetcher thread for Limitless standard (15 tournaments + one request per deck page + sprites). Refreshes every 15 s, but only while the window is **not** focused (protected interaction).

## 5. Limitless tournament flow (as designed vs actual)
Designed:
1. Background hidden page on `/dashboard` → every 60 s run the check-in scan JS.
2. If a check-in button is found → auto-click (or show alert).
3. If an active `/match/` link is found → load it in a hidden chat page → every 3 s extract chat → overlay chat bubble window + `.chat_capture.json`.
4. Opponent from chat header → `.in_tournament` → parser tags the battle as tournament (weight ×3).

Actual (because of BUG-001, BUG-008, BUG-017):
- Nothing loads in the background until the dashboard window is opened once.
- Even then, `_on_background_load_finished` throws `AttributeError`, so the 60 s poll timer **never starts**, and chat polling never starts either.
- The `inTournament` regex matches almost any dashboard page, so `.in_tournament` = `{"in_tournament": true, "opponent": ""}` sits on disk (current state).
- The parser never calls `is_tournament_battle()`, so no battle has ever been tagged (all 39 rows have `is_tournament=0`).

## 6. Replay
Battle row click → `open_battle_replay` → rebuild a throwaway WebEngine profile → load ptcglreplay.com → inject the log file via a JS `DataTransfer` drop. Fallback: Playwright (not installed) → default browser + Explorer selecting the log to drag in (`_open_replay_manually`).
