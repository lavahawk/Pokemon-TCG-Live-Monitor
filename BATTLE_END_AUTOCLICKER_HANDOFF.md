# Battle-End Auto-Clicker — Handoff Document

**Repo:** lavahawk/Pokemon-TCG-Live-Monitor (branch `main`)
**Last updated:** 2026-09-09 (commit `2e52099`)
**Author context:** Built iteratively through live debugging with the user. Read the
"Hard-Won Lessons" section before changing anything in this pipeline.

---

## 1. What This Does

When a Pokémon TCG Live battle ends, the system **automatically**:

1. Detects the battle ended (in-battle HUD disappears)
2. Shows a themed **Continue blocker** overlay over the game's Continue button
3. Clicks the **BATTLE LOG** button
4. Clicks the **battle log export** button (which copies the log to the clipboard)
5. Dismisses the blocker the instant the export lands on the clipboard (same moment the ding plays)
6. The existing clipboard monitor saves the log, plays the sound, and runs the AI parser

The mouse moves **exactly twice** per battle (once per button) and returns to its
original position after each click. The user never needs to touch anything.

---

## 2. Architecture / Data Flow

```
BattleState.py (HUD watcher thread, 2-3s poll)
    polls 3 color anchors: chat bubble, prize badge, timer panel (2-of-3 must hit)
    HUD present -> "in battle"
    HUD gone x3 consecutive checks (~6s) -> arm fast poll
        |
        v
_confirm_battle_log_visible(60s)  -- template match on BATTLE LOG button
        |  (template visible = real trigger; HUD alone can NOT fire)
        v
_launch_continue_blocker()  -> ContinueBlocker.py subprocess (topmost overlay)
run_battle_end_autoclicks() -> _battle_end_click_worker (daemon thread)
        |
        v
AutoClicker.click_button(mode="physical")  x2
    1. battle_log template -> physical click -> blocker launched
    2. battle_log_export template -> physical click
       retries verified via CLIPBOARD (is_battle_log), not button visibility
        |
        v
export puts log on clipboard
        |
        v
monitor_clipboard() detects it (content-hash dedupe skips echo)
    -> _signal_blocker_dismiss()   (writes Logs/.blocker_dismiss; blocker fades out)
    -> save_battle_log() -> play_sound() -> run_other_script() (AI parse)
    -> _sweep_orphan_blockers() after 2s (kills any stragglers)
```

### Key files

| File | Role |
|---|---|
| `TCGLiveMonitor.py` | Main monitor: clipboard loop, HUD watcher, click worker, blocker lifecycle, dedupe, forensics |
| `BattleState.py` | HUD color-anchor detector (`check_hud()`), standalone-testable (`python BattleState.py --once`) |
| `AutoClicker.py` | Template matching + physical clicking + cursor restore |
| `ContinueBlocker.py` | Topmost themed overlay covering Continue; comet border animation; fade in/out; hard-exits on dismiss |
| `SetupAutoClicker.py` | Interactive template capture tool (`--list`, `--delete NAME`) |
| `button_templates/` | `battle_log.png` (237x76), `battle_log_export.png` (48x52) — gitignored |
| `Logs/autoclicker.log` | Every clicker event, timestamped — **check this first when debugging** |
| `Logs/blocker_debug.log` | Blocker lifecycle debug |
| `Logs/unmatched_*.txt` | Forensic capture of clipboard blobs that failed battle-log detection |

---

## 3. Current Behavior (verified working)

- HUD watcher detects battle start/end via 2-of-3 color anchors (relative coords, resolution-independent)
- After HUD disappears: 60s high-rate window watching for the BATTLE LOG template
- On template confirmation: blocker appears (fade-in) → BATTLE LOG clicked → export clicked
- Export retries verify success via clipboard content (max 3 retries, 1s apart)
- Blocker dismisses when the log hits the clipboard (dismiss signal file, 100ms poll)
- 30s cooldown prevents the clipboard echo from re-running the click sequence
- 10-minute content-hash dedupe prevents double-saving the same log
- Cursor: saved before each click, restored ~250ms after mouse-up (Unity needs the delay)
- Orphan blocker sweep runs 2s after every sequence

---

## 4. Hard-Won Lessons (DO NOT REGRESS)

1. **mss is thread-bound.** An `mss.mss()` instance created in thread A raises
   `ThreadSafetyError` in thread B — silently, in a headless console. Always create
   per-call instances (`with mss.mss() as sct:`) inside `find_button`. This was the
   original "clicker never fires" bug (commit `7df0dcb`).

2. **PTCG Live (Unity) ignores PostMessage background clicks.** Only real cursor
   input (`SendInput` via pyautogui) registers. `mode="physical"` is mandatory for
   this game. Background click code is kept in AutoClicker for other windows.

3. **Unity cancels clicks if the cursor is restored instantly.** The game processes
   UI clicks a frame after mouse-up. Sequence: `moveTo → 80ms → mouseDown → 60ms →
   mouseUp → 250ms → restore`. Instant restore = click visually fires but the game
   ignores it (commit `952a5c9`).

4. **HUD detection is a trigger aid, not ground truth.** Arena themes change anchor
   colors; cards sliding over anchors cause flicker. Never fire clicks from HUD state
   alone — always confirm the BATTLE LOG template is actually visible (commit `4230f5c`).

5. **Victory/prize animations delay the BATTLE LOG button** well past 12s. The
   confirm window after HUD-gone must be ~60s (commit `54a4944`).

6. **Both the HUD watcher and the clipboard echo trigger the sequence.** The export
   click re-copies the log to the clipboard, re-triggering the monitor. The 30s
   `CLICK_SEQUENCE_COOLDOWN` in `run_battle_end_autoclicks` prevents double-runs;
   the 10-minute hash dedupe prevents double-saves (commits `4a5c5b5`, `48944cd`).

7. **Export retries must verify via clipboard, not button visibility.** The popup
   stays visible during its fade-out after a successful click, so visibility checks
   cause 3 extra cursor jumps. Clipboard check = exactly two mouse movements (commit `c8c1ec6`).

8. **Blocker processes must hard-exit.** Qt timers survive `close()`/`terminate()`
   surprisingly well; 12 orphans once accumulated and made the cursor glitchy.
   `os._exit(0)` on fade-out completion + the post-sequence orphan sweep guarantee
   zero footprint (commit `2e52099`).

9. **Blocker positioning must use win32 `SetWindowPos` in physical pixels** with
   `HWND_TOPMOST`, and must re-assert geometry every tick (Qt shrink-wraps the
   native window to layout sizeHint after `show()`). Use `RankDetector` for the
   game rect — `FindWindow` alone returns stale/shifted rects.

10. **Test scripts must call `load_template()` before `find_button()`** — it returns
    None silently otherwise. This caused two false-alarm debugging sessions.

11. **The headless monitor has no console.** All clicker events go to
    `Logs/autoclicker.log` via `_alog()`. Always check this file first.

---

## 5. Configuration Constants (TCGLiveMonitor.py)

```python
BATTLE_END_BUTTONS = [
    {"template": "battle_log", "timeout": 30, "desc": "BATTLE LOG button"},
    {"template": "battle_log_export", "timeout": 20, "desc": "battle log export button"},
]
BATTLE_END_POLL_INTERVAL = 0      # continuous; mss capture IS the interval
CLICK_SEQUENCE_COOLDOWN = 30      # dedupe watcher vs clipboard echo
```

`BattleState.py`:
```python
REQUIRED_HITS = 2            # of 3 HUD anchors
IN_BATTLE_POLL = 2.0         # seconds while watching a battle
HUD_GONE confirmations: 3 checks (~6s) before arming
BATTLE LOG confirm window: 60s after HUD gone
```

`ContinueBlocker.py`:
```python
BLOCKER_MAX_LIFE = 30        # failsafe lifetime
DEFAULT_REL = {"x": 0.50, "y": 0.955, "w": 0.32, "h": 0.11}  # over Continue
```

---

## 6. Debugging Playbook

1. **Open `Logs/autoclicker.log`** — every event is timestamped with per-anchor
   HUD readings and click results.
2. **No clicks fired?** Check for `Battle HUD detected` → `Battle HUD gone x3` →
   `BATTLE LOG button confirmed`. Whichever stage is missing tells you the problem:
   - No "HUD detected": anchors mismatched (arena theme?) — run `python BattleState.py --once` in-battle
   - "No BATTLE LOG button within 60s": template mismatch — recapture via `SetupAutoClicker.py`
   - "skipping duplicate trigger": cooldown hit (expected after echo)
3. **Clicked but game didn't respond?** Verify physical mode in the log; check the
   250ms restore delay is intact (Unity click cancellation).
4. **Blocker won't go away?** `_sweep_orphan_blockers` should reap it within 2s;
   check `Logs/blocker_debug.log`.
5. **Battle not saved at all?** Look for `UNMATCHED clipboard log` in
   autoclicker.log and open the newest `Logs/unmatched_*.txt` — it contains the raw
   text and which detection conditions failed.
6. **Duplicate battles in DB?** Check the dedupe: content hash + 10-minute window.

---

## 7. Known Quirks / Open Items

- **Monitor spawns duplicate processes** (venv python + system python via
  interpreter-level spawn). The `.monitor_lock` dedupes; restarts should kill all
  `TCGLiveMonitor`/`OverlayUI` processes first, then remove `.monitor_lock`.
- **HUD anchors are theme-sensitive.** The 2-of-3 + template-confirmation design
  tolerates theme variation, but a radically different arena could drop below 2/3
  hits. If battles stop being detected, capture a screenshot of the new theme and
  recalibrate `check_hud()` anchors (chat ~ (0.022, 0.59), prize ~ (0.225, 0.862),
  timer ~ (0.975, 0.30) — relative coords).
- **Blocker position** is relative to the live game rect and re-verified every
  200ms; if the Continue button moves in a game update, adjust `DEFAULT_REL`.
- **Templates are resolution-tied to capture time.** If the game window size changes
  dramatically (new monitor, DPI change), recapture both templates. (Multi-scale
  matching was prototyped — best score 0.67 at 0.7x — but not shipped; consider
  adding it to `find_button` if template misses recur.)
- **The missed battle from 2026-09-09 ~08:00 is unrecoverable** (clipboard empty,
  pre-forensics build). Replay via the in-game log viewer if needed.

---

## 8. Commit History (this feature)

| Commit | Summary |
|---|---|
| `7df0dcb` | mss thread-safety fix (clicker never fired) + file logging + clicks before sound |
| `ec24fd3` | Cursor restore after each physical click |
| `952a5c9` | Unity click timing (settle/hold/250ms before restore) |
| `4a5c5b5` | Dedupe export echo (10-min content hash) |
| `ba23b61`/`cc40d25` | Continue blocker overlay + polish (comet border, fades, geometry re-assert) |
| `b614c2d` | Forensics for unmatched clipboard blobs |
| `9ff176d` | Battle-state HUD watcher (the trigger) |
| `4230f5c` | False-trigger gates (HUD-gone 6s + template confirmation) |
| `54a4944` | 60s BATTLE LOG confirm window |
| `48944cd` | 30s click-sequence cooldown (double-run fix) |
| `06f2b6a` | Blocker dismiss synced to export/clipboard (the ding) |
| `c8c1ec6` | Exactly two mouse movements (clipboard-verified retries) |
| `2e52099` | Hard-exit blocker + orphan sweep (cursor glitch fix) |

---

## 9. Quick Reference — Manual Operations

```powershell
# Restart the monitor (kills duplicates, removes lock)
Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe'" |
  Where-Object { $_.CommandLine -like "*TCGLiveMonitor*" -or $_.CommandLine -like "*OverlayUI*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Remove-Item .monitor_lock -Force -ErrorAction SilentlyContinue
Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "TCGLiveMonitor.py","--headless" `
  -WorkingDirectory "C:\Users\2awso\Downloads\BattleLogImport" `
  -WindowStyle Hidden -PassThru

# Test HUD detection right now
.\.venv\Scripts\python.exe BattleState.py --once

# Kill orphaned blockers
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like "*ContinueBlocker*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# Recapture button templates (after game UI updates)
.\.venv\Scripts\python.exe SetupAutoClicker.py
```

**Launch quirk (critical):** detached `pythonw.exe TCGLiveMonitor.py` dies silently.
Use the `Start-Process` command above with the venv `python.exe`, then verify
`HasExited == False` and `.monitor_lock` exists after ~10s.
