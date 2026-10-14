---
tags: [findings, bugs]
updated: 2026-10-11
---
# Bug Register

> [!success] v2.4 (2026-10-11): every item marked `fixed (v2.4)` was changed and verified offscreen. Each fix is described in [[Session Log]]. **Confirmed in a real game (2026-10-11):** BUG-014 auto-export, after fixing BUG-037/038. **Still to confirm on Windows:** BUG-009 (auto-start at login), BUG-010 (GDI).

**Status values:** `open` · `in-progress` · `fixed` · `wontfix` · `needs-info`
**Confidence:** `confirmed` (reproduced or visible in real data/logs) · `code` (certain from reading the code, not executed) · `likely` (strong inference; needs a check on Windows)
**Severity:** Critical / High / Medium / Low — about user impact, not how hard the fix is.
Security items live in [[Security and Privacy Review]]; data damage already done is in [[Data Integrity Audit]].
Line numbers are from the 2026-10-11 snapshot.

## Summary table
| ID | Sev | Conf | Status | Area | One-liner |
|---|---|---|---|---|---|
| BUG-001 | High | confirmed | fixed (v2.4) | [[Limitless Dashboard Manager]] | `__init__` tail mis-indented into `_tournament_poll`, so poll and chat timers never exist and auto check-in is dead |
| BUG-002 | High | confirmed | fixed (v2.4) | [[TCGLiveMonitor]] | Same battle log saved as several battles (5/39 rows); dedupe is in-memory and only 10 min |
| BUG-003 | High | code | fixed (v2.4) | [[Startup and Installers]] | No installer ships `japan_data.py`, `BattleState.py` or `ContinueBlocker.py`, so StatsUI ImportError; Inno `[Run]` uses `{sys}\python.exe`; setup.iss installs to Program Files (read-only) |
| BUG-004 | High | confirmed | fixed (v2.4) | [[BattleDatabase]] | Timestamps are UTC, session dates are local, and the UI shows raw UTC |
| BUG-005 | Med | confirmed | fixed (v2.4) | [[AIParseBattleLog]] | `local_fallback_parse` raises `UnboundLocalError: inferred` when a console user types the opponent's deck |
| BUG-006 | Med | code | fixed (v2.4) | [[TCGLiveMonitor]] | Post-battle OCR does `UPDATE battles … WHERE id=MAX(id)` even if this battle wasn't saved, overwriting the previous battle |
| BUG-007 | Med | confirmed | fixed (v2.4) | [[deck_analytics]] | Rank weighting assumes 1500–1900 Elo; real ranks are 3–260, so every weight is 0.15 and the metric is meaningless |
| BUG-008 | Med | confirmed | fixed (v2.4) | [[AIParseBattleLog]] | `is_tournament_battle()` is never called, so `is_tournament` is always 0 |
| BUG-009 | High | likely | fixed (v2.4) | [[TCGLiveMonitor]] | Headless (`pythonw`) has `sys.stdin=None`, so `sys.stdin.isatty()` raises AttributeError at import |
| BUG-010 | Med | code | fixed (v2.4) | [[RankDetector and BattleState]] | `mss.mss()` per `RankDetector()`/`AutoClicker()` is never closed, so GDI handles leak every 2–3 s |
| BUG-011 | Med | confirmed | fixed (v2.4) | [[TCGLiveMonitor]] | Logs are written in the cp1252 default but read as UTF-8 ("Pok�mon"); non-cp1252 chars raise in the save |
| BUG-012 | Med | confirmed | fixed (v2.4) | [[AutoClicker and ContinueBlocker]] | `pyautogui` is in neither requirements nor installers, so the auto-clicker is silently disabled on fresh installs |
| BUG-013 | Med | code | fixed (v2.4) | [[Startup and Installers]] | `INSTALL_COMPLETE_v2.3.bat` pins `openai==1.12.0` (crashes with httpx ≥0.28); unquoted `>=` creates junk files |
| BUG-014 | Med | confirmed | fixed (v2.4) | [[AutoClicker and ContinueBlocker]] | Click sequence races: two blockers, BATTLE LOG re-clicked after a manual export, a battle missed on 09-13 22:26 |
| BUG-015 | Low | confirmed | fixed (v2.4) | [[StatsUI]] | "Open OCR Test Window" passes `--ocr-test`, which argparse doesn't know |
| BUG-016 | Low | code | fixed (v2.4) | [[Startup and Installers]] | `enable_startup()` deletes the backup scheduled task it just created |
| BUG-017 | Med | confirmed | fixed (v2.4) | [[Limitless Dashboard Manager]] | `inTournament` regex matches nearly any page; stale `.in_tournament` flag; flag flaps |
| BUG-018 | Med | code | fixed (v2.4) | [[TCGLiveMonitor]] | Single-threaded loop: sound + parser + menu OCR block capture for up to ~5 min |
| BUG-019 | Low | confirmed | fixed (v2.4) | [[OverlayUI]] | `.overlay_debug.log` grows without bound (11.4 MB), one write per second |
| BUG-020 | Med | confirmed | fixed (v2.4) | [[OverlayUI]] | OCR misreads (rank 3, 4, 20) go into `rank_history`; the "+30 guard" exists only in comments; Max/Elo graph not protected; `Fix_MaxRank` option 2 is a no-op |
| BUG-021 | Low | confirmed | fixed (v2.4) | [[RankDetector and BattleState]] | OCR deck names like "Oragaputt", "VidQGd Pull…" override `my_deck` and fragment deck stats |
| BUG-022 | Med | likely | fixed (v2.4) | [[StatsUI]] | Closing the dashboard during a meta fetch destroys a running QThread, which can abort the overlay process |
| BUG-023 | Low | confirmed | fixed (v2.4) | [[AIParseBattleLog]] | Winner regex `[A-Za-z0-9_-]+`: names with `.`/spaces/unicode give the wrong Win/Loss |
| BUG-024 | Low | code | fixed (v2.4) | [[BattleDatabase]] | `get_all_time_stats` filters `my_rank IS NOT NULL`, so totals drop when OCR fails |
| BUG-025 | Low | code | fixed (v2.4) | [[RankDetector and BattleState]] | `find_game_window` substring title match also hits "Pokemon TCG Live Monitor – Startup Manager" and browser tabs |
| BUG-026 | Low | code | fixed (v2.4) | [[RankDetector and BattleState]] | Regions with negative coords (monitor left/above primary) are rejected, so OCR is dead there |
| BUG-027 | Med | confirmed | fixed (v2.4) | [[japan_data]] | Frozen source slugs; rows show 100% WR; first-substring translation; wrong translations; duplicate keys; 2 AI calls per name |
| BUG-028 | Low | code | partial | [[StatsUI]] | Heavy dashboard: eager WebEngine views, rebuild every deck page, geometry written per pixel, refresh paused while focused |
| BUG-029 | Low | code | fixed (v2.4) | [[TCGLiveMonitor]] | Import-time side effects run before the single-instance check (second launch clears console / prompts) |
| BUG-030 | Low | code | fixed (v2.4) | [[AIParseBattleLog]] | Excel sheet name not sanitized (`[]:*?/\`), so the workbook update fails |
| BUG-031 | Low | code | fixed (v2.4) | [[AIParseBattleLog]] | OpenAI client has no timeout; 3-model fallback can exceed the monitor's 180 s kill, so nothing is saved |
| BUG-032 | Low | code | fixed (v2.4) | [[OverlayUI]] | Liveness uses `psutil.pid_exists`, so a recycled PID keeps an orphan overlay alive |
| BUG-033 | Low | code | fixed 2026-10-14 | [[StatsUI]] | Replay fallback: Playwright not installed and the helper's errors go to DEVNULL, so it fails silently |
| BUG-034 | Low | confirmed | fixed 2026-10-14 | various | Code health: `\(` SyntaxWarning in banner, unused vars, stale VERSION strings, no-assert test, dead code, doc drift |
| BUG-036 | High | confirmed | fixed (v2.4) | [[Startup and Installers]] | Pinned packages (numpy 1.26, pandas 2.2, pygame 2.5, pydantic 2.6, matplotlib 3.8) have no wheels for Python 3.13, so pip fails on fresh PCs with the current python.org default. bootstrap_setup.ps1 now finds or installs Python 3.12 |
| BUG-035 | Low | code | fixed (v2.4) | [[TCGLiveMonitor]] | `pyperclip.copy('')` wipes the user's clipboard every time the game starts |
| BUG-037 | Critical | confirmed | fixed (v2.4) | [[BattleEndAutomation]] | Real game, home screen: BATTLE LOG template matched a dark bar beside PLAY (0.84) and clicked it twice; the wrong spot was then cached. Fix: OCR must read "BATTLE LOG" in the matched box before any click; unverified positions are never cached |
| BUG-038 | High | confirmed | fixed (v2.4) | [[RankDetector and BattleState]] | Colour-patch HUD check matched an old layout: 3/3 "in battle" on the home screen, 1/3 during real matches. Replaced by a settings-gear template (battle 0.98–1.00, home 0.44); BATTLE LOG search no longer paused while the HUD shows |
| BUG-039 | Med | confirmed | fixed (v2.4) | [[Startup and Installers]] | Script installers download Python, pip-install ~1 GB and fetch Tesseract on the user's PC, so they fail offline, behind proxies or with AV. Replaced by an offline Inno Setup bundle (Python 3.12 runtime + packages + minimal Tesseract) with a build-time smoke test |
| BUG-040 | Low | confirmed | fixed (v2.5) | [[TCGLiveMonitor]] | Post-battle menu OCR read the deck but `rank=None` (battles #46, 48, 50, 52, 53): the points counter was still animating. `detect_menu_stats` now keeps reading until the value settles. Verified live: 13/13 after-battle reads stored a rank (#57–#69, 2026-10-12/13) |

## Details

### BUG-001: Limitless manager never finishes initializing
- **Where:** `StatsUI.py` L676–733. AST check: `__init__` ends at L709; L723–733 (`delayed_poll_timer`, `chat_poll_timer`, `_load_state()`, `_ensure_profile()`) sit inside `_tournament_poll`.
- **Repro:** `04 Dev/scripts/repro.py` → `hasattr(m,'delayed_poll_timer') == False`; `_on_background_load_finished()` raises `AttributeError`, and so does `_on_chat_page_load_finished()`.
- **Effect:** no background dashboard at startup; once a view registers, the load-finished slot throws before `poll_timer.start()`, so no 60 s check-in polling and no chat polling. If `_tournament_poll` ever runs, it creates 2 new QTimers every 10 s (leak) and re-reads state from disk.
- **Fix:** move L723–733 back into `__init__` (before `_tournament_poll`). Add a unit test that constructs the manager offscreen.

### BUG-002: Duplicate battle records
- **Where:** `TCGLiveMonitor.monitor_clipboard` L333–372 (dedupe is `last_battle_log_hash` in memory, 600 s window, hash of raw clipboard text).
- **Evidence:** [[Data Integrity Audit]]: identical log content saved and parsed as separate battles: #29 = #28 (7 min apart), #34/#35/#36 = #33 (1–2 h apart), #4/#5 share one log file. `autoclicker.log` 02:59:01 and 02:59:07 show two sequence starts inside the 30 s cooldown, which suggests 2 monitor instances at the time (pre-lock).
- **Fix:** store `log_sha256` (normalized: CRLF→LF, stripped) in `battles` with a UNIQUE index; check before saving and parsing; keep the in-memory check as a fast path. Add a one-time cleanup script (backup first).

### BUG-003: Release packaging out of sync
- `installer_setup.iss`, `installer_portable.iss`, `Create_Portable_Installer.py` (L528+) and `Build_Release_Package.bat` all omit `japan_data.py` (a hard import at `StatsUI.py` L34), `BattleState.py`, `ContinueBlocker.py`, `SetupAutoClicker.py` and `button_templates/`.
- `[Run] Filename: "{sys}\python.exe"`: Python is not in System32, so post-install setup never runs.
- `installer_setup.iss` installs to `{autopf}` (Program Files), but the app writes its DB, logs and caches next to the code, which fails or gets VirtualStore-redirected for a normal user.
- **Fix:** one manifest file (e.g. `release_manifest.txt`) consumed by all four builders; data dir → `%LOCALAPPDATA%\PTCGLMonitor`; run setup via `{app}\.venv` or `py.exe`.

### BUG-004: UTC vs local time
- `battles.timestamp DEFAULT CURRENT_TIMESTAMP` (UTC); `update_session_stats` uses `datetime.now().date()` (local); `rebuild_session_stats` uses `DATE(timestamp)` (UTC); UI formats the raw UTC.
- **Repro:** `rebuild_session_stats()` on a copy of the real DB turns 09-08 `4-2` / 09-09 `2-3` / 09-13 `2-0` into 09-08 `4-1` / 09-09 `3-10` / 09-10 `2-3` / 09-14 `2-0`. The screenshot shows "09/14 01:48" for a game played 09/13 21:48.
- **Fix:** store UTC ISO with `Z` or store local explicitly; convert on display; group by `DATE(timestamp,'localtime')`. Migrate existing rows (all are UTC today).

### BUG-005: Local-mode crash
- `AIParseBattleLog.py` L353–372: `inferred` is only assigned inside `if not opponents_deck:`, then read at L371.
- **Repro:** repro.py, case P1. **Fix:** `inferred = None` up front, or compute it unconditionally.

### BUG-006: Post-battle OCR overwrites the wrong row
- `TCGLiveMonitor.py` L849–865. If the parser timed out, crashed (BUG-005) or was skipped, the update lands on the previous battle. It also changes `my_rank` from pre-battle to post-battle semantics (the parser stores `.last_rank` = pre-battle).
- **Fix:** have the parser return or print the new battle id (or write `.last_battle_id`), then update by id; decide one rank semantic (recommend storing both `rank_before` and `rank_after`).

### BUG-007: Rank weighting mis-calibrated
- `deck_analytics.py` L128–166: `MASTERBALL_ELO=1500`, `FULL_WEIGHT_ELO=1700`. DB ranks: min 3, max 260. `rank_weight(30..260) == 0.15` for all of them.
- The "Pult Hammers" deck gets `effective_n = 3.6` from 24 games and is always "Low" confidence. The docstring also claims weight(1500)=0.5, but the code gives 0.575.
- **Fix:** derive thresholds from the in-game league table (OverlayUI uses 30/110/230/390/550). Needs info from Lva.

### BUG-008: Tournament tagging is never applied
- `is_tournament_battle()` (L97) has zero call sites; `save_to_database(... is_tournament=False)` default. All 39 rows have `is_tournament=0`.
- **Fix:** call it in `main()` once BUG-017 makes the flag trustworthy.

### BUG-009: Headless crash (needs confirmation)
- `TCGLiveMonitor.py` L220 `IS_TERMINAL = sys.stdin.isatty()` runs at import. Under `pythonw.exe` (Run_Headless, registry Run key, scheduled task) `sys.stdin is None`, so it raises AttributeError before anything else.
- **Check on Windows:** `.venv\Scripts\pythonw.exe TCGLiveMonitor.py --headless` and see if `.monitor_pid` appears. **Fix:** `IS_TERMINAL = bool(sys.stdin and sys.stdin.isatty())`.

### BUG-010: GDI handle leak
- mss 9.0.1 on Windows calls `GetWindowDC` + `CreateCompatibleDC` in `__init__` and frees them only in `close()` (verified in the wheel source; no `__del__`).
- `RankDetector.__init__` keeps `self.sct = mss.mss()`; `BattleState.check_hud()` constructs a `RankDetector()` on every poll (2–3 s); `_get_battle_end_clicker()` constructs one per watcher tick; `AutoClicker.__init__` also creates an unused `self.sct`; ContinueBlocker constructs one every 200 ms.
- Windows' per-process GDI limit is 10,000, so a long session could exhaust it, at which point captures fail silently. **Fix:** lazy, per-thread mss with `with mss.mss()` (as `find_button` already does), and a cached window lookup.

### BUG-011: Log file encoding
- `save_battle_log` L314 `open(filename, "w")` with no encoding, so cp1252 on Windows. Every reader uses UTF-8 → "Pok�mon" in parser/AI input and replay injection (visible in real logs). Characters outside cp1252 raise `UnicodeEncodeError`, which is uncaught and kills the monitor loop.
- **Fix:** `encoding="utf-8", newline="\n"`; re-encode existing logs once.

### BUG-012: Missing dependency `pyautogui`
- Imported by `AutoClicker.py` L9; `TCGLiveMonitor` wraps the import in try/except and sets `AUTOCLICKER_AVAILABLE=False`. It isn't in `requirements.txt`, `setup_install.py` or the install bats. (`mouse` is in requirements but not in the install bat.)

### BUG-013: Installer bat dependency drift
- `INSTALL_COMPLETE_v2.3.bat` installs `openai==1.12.0`; `requirements.txt` explicitly says ≥1.35 or it crashes with "unexpected keyword argument 'proxies'". So AI parsing always falls back to local on bat-based installs.
- `pip install beautifulsoup4>=4.12.0 …` unquoted in cmd: `>` is a redirect, so files named `=4.12.0` etc. are created and versions are unpinned. `%errorLevel%` is only checked after the last pip.
- **Fix:** bat should just `pip install -r requirements.txt`.

### BUG-014: Battle-end auto-click races
- Evidence (`Logs/autoclicker.log`, `blocker_debug.log`): most sequences start *after* the log already arrived and then report "export button not found". At 21:19:52 it clicked BATTLE LOG after the log was already saved (re-opens the popup on the user). At 22:26:52 the watcher fired, two blockers were launched (22:26:52 + 22:26:54), the export never happened, and that battle is missing (no log after 21:48:12). At 02:59 the export retried 3× even though the log landed (the clipboard read from the worker thread probably raced the main loop).
- Causes: the watcher path calls `_launch_continue_blocker()` and then the worker launches another; the clipboard path calls `run_battle_end_autoclicks()` even when the user exported manually; `_block_continue_button` uses `mouse.hook`, which can't suppress clicks (no-op), and its fallback `unhook_all()` removes every hook.
- **Fix:** run the sequence only from the watcher; on the clipboard path, never click; one blocker per sequence; drop `_block_continue_button`.

### BUG-017: Tournament state heuristic
- `_checkin_scan_js` `tournamentHints = /check-in|enrolled|registered|tournament|round \d+|rounds?|standings|decklist|match/`, which is true for nearly any logged-in dashboard. `_handle_checkin_scan_result` then writes `{"in_tournament": true, "opponent": ""}` (the current on-disk file is exactly this), overwriting the opponent captured from chat. `_publish_chat_state` clears it again when the chat has no opponent, so it flaps. The flag is never removed on exit.
- **Fix:** derive "in a match" only from an active `/match/` page with an opponent; add a TTL (`captured_at`) and ignore stale flags.

### BUG-018: Blocking main loop
- `play_sound()` blocks until the mp3 ends; `subprocess.run(parser, timeout=180)`; `wait_for_main_menu_and_detect()` up to 120 s. While these run, the clipboard isn't watched, so a quick next game (or a manual re-export) can be missed or merged.
- **Fix:** a capture thread that only saves logs to a queue; a worker that parses and does OCR.

### BUG-020: Rank sanity
- `rank_history` contains OCR misreads (3, 4, 20 among 30–260 neighbours); the Elo chart shows the spikes. `get_max_rank()` = `MAX(rank)`, so one high misread (e.g. 2600 for 260) would stick forever. Comments in `detect_initial_stats` refer to a "+30 max-gain guard" that doesn't exist anywhere. `Fix_MaxRank.py` option 2 writes `.max_rank`, which is only read when the DB has no ranks, so it does nothing.
- **Fix:** reject OCR reads that differ from the last accepted rank by more than N unless confirmed twice; mark rows `source='ocr'` and keep raw text.

### BUG-022: QThread lifetime
- `MetaFetcher`/`JapanFetcher` are created without a parent and stored on the `StatsWindow` (`WA_DeleteOnClose`); the overlay drops its reference on close. If the window is collected while `run()` is still going (Limitless fetch = 15 tournaments + N deck pages), Qt aborts with "QThread: Destroyed while thread is still running", killing the overlay.
- **Fix:** parent the threads to the app or the manager, keep a module-level registry, and `wait()` on close.

### BUG-027: Japan data
- Slugs are hard-coded (last tournament page 2026-08-16, data lab `m6-3w`), so the tab never updates.
- `_consolidate_rows` sets `wins=count, losses=0`, so the Raw WR column is 100%, Bayes ≈78–99% and P>50 ≈100% for every Japanese deck (meaningless).
- Substring translation returns the first dict key found, not the longest: `メガゲッコウガex` → "Greninja"; multi-Pokémon names collapse to the first.
- Duplicate keys in `JP_DECK_TRANSLATION`: ガブリアス ("Garchomp" overrides "Cynthia's Garchomp"), フーディン, ガルーラボックス, タケルライコ, ドデカバシ, メガヤンマ.
- Wrong translations (high confidence): ドデカバシ = Toucannon (not Dondozo), イワパレス = Crustle (not Garganacl), カミツオロチ = Hydrapple (not Iron Thorns ex), ダイオウドウ = Copperajah, ガチゴラス = Tyrantrum, イトマル = Spinarak, ベラカス = Rabsca, イイネイヌ = Okidogi, パンプジン = Gourgeist, ガラルファイヤー = Galarian Moltres, マッギョ = Stunfisk, ヒガナ = Zinnia. Several entries look invented (ご幸非, マンデー, キノノタミ, メガシンヤ).
- On hard refresh, `_ai_translate` is called **twice per name**, one name at a time, so 2N gpt-4o calls. `hard_refresh_translations()` (batched) exists but is unused. `StatsUI.JP_DECK_TRANSLATION` is a dead stale copy.

### BUG-028: Dashboard weight and refresh
- Every open builds the Limitless, ptcglreplay and pokedata `QWebEngineView`s and starts loading them (even if those tabs are never viewed).
- `load_stats` every 15 s rebuilds all deck analyses (several queries per deck); `_refresh_deck_dashboards` recreates every deck page and its matplotlib canvas.
- `resizeEvent`/`moveEvent` write JSON on every pixel; the opacity slider re-applies the full stylesheet per tick.
- `begin_protected_interaction` stops the refresh timer whenever the window is active, so it doesn't refresh while you look at it, yet keeps refreshing while hidden via ▼.

### BUG-034: Code health (batch)
`TCGLiveMonitor.py:194` invalid escape `\(` (SyntaxWarning now, error in future Python); pyflakes unused vars (`OverlayUI:610`, `RankDetector:232`, `StatsUI:3538,3662,5859`, `startup_utils:212`); `VERSION="2.1"` in Overlay/Stats; `test_rank_weighted.py` prints and asserts nothing; dead code: `OverlayUI.calculate_session_stats`, `AutoClicker.watch_and_click`, `japan_data.hard_refresh_translations`, `StatsUI.JP_DECK_TRANSLATION`, `BattleState.wait_for_battle_end`; README says the overlay is click-through (it isn't by design anymore); `Install_Dependencies.bat` uses global `pip`, not the venv.

## Suggested fix order
1. **Quick wins (small diffs, high value):** BUG-001, BUG-005, BUG-009 (after confirm), BUG-011, BUG-015, SEC-01, BUG-012/013.
2. **Data correctness:** BUG-002 (+ cleanup script), BUG-004 (+ migration), BUG-006, BUG-020, BUG-021, BUG-024.
3. **Features that currently do nothing:** BUG-017 → BUG-008 (tournament pipeline), BUG-007 (needs rank table), BUG-014 (auto-clicker).
4. **Release pipeline:** BUG-003, BUG-016, SEC-06, SEC-11.
5. **Robustness/perf:** BUG-010, BUG-018, BUG-019, BUG-022, BUG-028.
6. **Japan tab:** BUG-027.
7. **Structure:** split `StatsUI.py` (8.2k lines) into a package: `limitless/`, `meta/`, `tabs/`, `widgets/`; add pytest with the harness from [[Dev Environment and Test Harness]].
