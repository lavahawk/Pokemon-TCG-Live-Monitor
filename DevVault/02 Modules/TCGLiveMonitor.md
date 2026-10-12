---
tags: [module]
file: TCGLiveMonitor.py
lines: 1064
---
# TCGLiveMonitor.py: the orchestrator

> [!info] Rewritten in v2.4. The table below describes v2.3, kept for history. v2.4 structure: `setup_output()` (Tee to `Logs/monitor.log`, pythonw-safe) → single instance → `Monitor.run()`: idle every 5 s on the process check (below-normal priority) → when the game runs, start the overlay + [[BattleEndAutomation]], then watch `GetClipboardSequenceNumber` every 0.5 s → `handle_clipboard` (hash dedupe in memory + DB, UTF-8 save, notify automation, async ding) → worker thread: parser (`BATTLE_ID=`) → `detect_menu_stats(update_battle_id=…)` with confirmed rank reads and deck-name snapping. `--ocr-test` runs a one-shot OCR diagnostic.

**Role:** main process. Shows the console banner, holds the single-instance lock, starts the overlay, runs the HUD watcher thread, polls the clipboard, saves logs, launches the parser, and runs post-battle OCR. See [[Process Map]] §1–2.

## Key functions
| Function | Lines | What it does |
|---|---|---|
| module top | 1–245 | **Side effects at import**: `cls`, banner, username prompt, `IS_TERMINAL = sys.stdin.isatty()` (BUG-009, BUG-029) |
| `_acquire_single_instance` | 85–148 | `msvcrt.locking` on `.monitor_lock`; PID-file fallback elsewhere |
| `is_battle_log` | 255–278 | Heuristic: ≥120 chars + turn header + result line (+ `Setup` and ≥3 action verbs for the new format) |
| `read_stable_clipboard` | 281–301 | Up to 4 reads, 0.25 s apart; returns the first repeated value |
| `monitor_clipboard` | 333–404 | Main loop. In-memory hash dedupe (600 s) (BUG-002); unmatched dump (SEC-01) |
| `save_battle_log` | 308–317 | No encoding (BUG-011); filename at 1 s resolution |
| `_battle_state_watcher` | 671–723 | HUD present → gone ×3 → watch for the BATTLE LOG template → blocker + clicks |
| `_battle_end_click_worker` | 566–636 | Click BATTLE LOG → blocker → click export (+≤3 retries) → close blocker → sweep orphans after 2 s |
| `_block_continue_button` | 452–494 | `mouse.hook` returning False, which **cannot** suppress clicks (no-op); `unhook_all` fallback is dangerous |
| `run_other_script` | 764–783 | `subprocess.run(parser, timeout=180)`, then **blocks** in `wait_for_main_menu_and_detect` |
| `wait_for_main_menu_and_detect` | 785–896 | OCR menu (≤120 s) → `.last_deck`, `.last_rank`, `rank_history`, `UPDATE … WHERE id=MAX(id)` (BUG-006) |
| `detect_initial_stats` | 919–995 | Same OCR at startup (≤60 s) |

## Gotchas
- Two triggers can start the click sequence (watcher + clipboard); a 30 s global cooldown dedupes them, but the clipboard trigger fires *after* the log already exists (BUG-014).
- The `--ocr-test` flag that StatsUI passes doesn't exist (BUG-015).
- `print()` is used as a log everywhere; nothing is visible in headless mode except `_alog` → `Logs/autoclicker.log`.
- `wait_for_game_startup` wipes the clipboard (BUG-035).

Related bugs: BUG-002, 006, 009, 011, 014, 018, 029, 035, SEC-01.
