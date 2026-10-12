---
tags: [log]
---
# Session Log
Append newest at the bottom. Format: date, who, what was done, what's next.

## 2026-10-11 — Claude (Phase 1: review)
**Did:**
- Read every Python module end to end (16.2k lines), all launchers/installers/Inno scripts, README/release notes and the auto-clicker handoff doc.
- Staged copies of the code, DB, logs and state files into a sandbox; ran import tests, a reproduction harness, a log/DB integrity audit, and rendered the dashboard offscreen with real data.
- Wrote this vault: architecture, process map, data model, 11 module notes, bug register (35 bugs), security review (11 items), data integrity audit.

**Confirmed by execution:** BUG-001, 004, 005, 007, 008, 023, 027; matplotlib/PySide6 compatibility OK. **Confirmed from data/logs:** BUG-002 (5 duplicate rows), 011, 014, 019, 020, 021, SEC-01 (code).

**Not touched:** no source file, DB or setting on the PC was modified. The only addition to the project folder is this `DevVault/`.

**Next:** get answers to [[00 Start Here#Open questions for Lva]] → start fix batch 1 ([[Bug Register#Suggested fix order]]). Back up `tcg_battles.db` before any data change.

## 2026-10-11 (later) — Claude (Phase 2: v2.4 fixes)
**Context / decisions from Lva:** auto-start (hidden, low CPU until the game runs) is the main mode and the installer must work; a terminal window is debug mode. Rank leagues = overlay thresholds. DB cleanup approved. Auto-export must work end to end. **No Claude co-author/attribution lines in commits.** Claude should do the git pushes.

**How the work was done:** the device shell (VM) failed to start, so code was edited in the cloud sandbox on copies and written back to the PC with file sync. Originals of every replaced file: `Backups/pre-v2.4-code/`. DB backup: `Backups/tcg_battles.backup_2026-10-11.db`.

**Data:** removed duplicate rows 5, 29, 34, 35, 36 and test row 11. Record is now 18-15.

**New modules**
- `game_window.py`: exact-title game window lookup, a cached handle, the foreground check and the DPI awareness setup. It replaces the 3 different window finders.
- `BattleEndAutomation.py`: the reworked auto-export state machine (see [[AutoClicker and ContinueBlocker]] and the handoff doc).
- `leagues.py`: ladder league thresholds and weights (overlay + analytics).
- `bootstrap_setup.ps1`: finds or installs Python 3.12, then runs `setup_install.py`. Used by every installer.
- `installer_common.iss`: shared Inno parts. `release_manifest.txt`: the single shipped-file list.

**Rewritten:** `TCGLiveMonitor.py` (pythonw-safe, idle loop, clipboard sequence number, DB-hash dedupe, worker thread for parse + OCR, `--ocr-test`), `BattleDatabase.py` (schema v2 migration, local time, `log_hash` UNIQUE, spike cleanup, resets survive rebuild, column whitelist), `AutoClicker.py` (multi-scale + ROI cache + ctypes clicks), `BattleState.py`, `setup_install.py`, installers/bats.
**Patched:** `AIParseBattleLog.py`, `StatsUI.py` (BUG-001 indent, tournament flag, URL allowlists, clipboard access removed, QThread lifetime, debug buttons, auto-export toggle, Japan columns, geometry debounce, sprite paths), `OverlayUI.py`, `RankDetector.py`, `ContinueBlocker.py`, `SetupAutoClicker.py`, `japan_data.py`, `deck_analytics.py`, `startup_utils.py`, `requirements.txt` (dropped xlwings/mouse; pyautogui not needed).

**Verified here (Linux sandbox, offscreen Qt, Windows APIs stubbed):**
- Simulated `pythonw` (stdin/stdout = None): old monitor → `AttributeError … isatty`; v2.4 starts, logs to `Logs/monitor.log`, idles.
- Monitor pipeline on a DB copy: an already-stored log is ignored (hash), a new log is saved + parsed (`BATTLE_ID` → post-battle update targets that id), the clipboard echo is ignored, ordinary copied text is never written to disk.
- DB migration on the real DB copy: timestamps converted (10:00Z → 05:00 EST, 01:20Z → 21:20 EDT), 33/33 hashes backfilled, spikes removed, idempotent, safe with 4 concurrent openers.
- Matcher: finds BATTLE LOG/export at window heights 720/900/1136/1440 (0.63–1.27× scale), no false positives on the battle screen; ~5–8 ms per poll after the first hit.
- Automation simulator (6 scenarios): auto export, user exported first (no clicks), game unfocused (no clicks), swallowed first click (re-click), export never lands (2 retries), lingering end screen + next battle (handled once each).
- Parser on all 48 real logs: winner/opponent correct for every one; local-mode crash gone.
- Release ZIP built from the manifest and every module imports from it. `bootstrap_setup.ps1` parses (pwsh 7.4). `test_rank_weighted.py`: 7/7 pass.
- Dashboard rendered with the migrated DB (local times, 33 games, 54.5%).

**Not verifiable here (needs the real PC):** live auto-start at login, real clicks in PTCGL, Tesseract OCR, Inno compile, pip install on Windows.

### Windows verification checklist
1. Close any running monitor/overlay (Task Manager → python/pythonw), then run `Install_Dependencies.bat` once (keeps your auto-start setting; reuses `.venv` if it's Python 3.10–3.12).
2. Debug run: `Run_TCGLiveMonitor_Command_Prompt.bat`. Expect "Monitor v2.4 starting … Waiting for Pokemon TCG Live…". The first start migrates the DB (one time).
3. Open PTCGL → overlay appears; play a game; at the end screen watch `Logs\autoclicker.log`: "BATTLE LOG button visible" → "Clicked BATTLE LOG" → "Clicked export" → "Auto-export complete". The dashboard shows the battle with local time.
4. If the BATTLE LOG button is never seen: run `.venv\Scripts\python.exe SetupAutoClicker.py` to recapture both templates (now works on any monitor).
5. Auto-start: `.venv\Scripts\python.exe AutoRun_Add.py`, sign out and back in, then check that `Logs\monitor.log` shows "(… headless)" and "Waiting…".
6. Installer: `Build_Inno_Installer.bat` (needs Inno Setup 6) → run Setup.exe on a test account.

### Git
GitHub isn't linked to this Claude account (`add_repo` → "link your GitHub account"), and the PC shell was unavailable, so **nothing is committed or pushed yet.** Either link GitHub in claude.ai Settings → Connectors so Claude can push, or run on the PC:
```
cd %USERPROFILE%\Downloads\BattleLogImport
git add -A
git commit -m "v2.4: fix auto-start, rework battle-end auto-export, installers, data integrity and Limitless fixes"
git push
```
(`DevVault/` is included; `Backups/` is gitignored.)


## 2026-10-12 — Claude (Phase 3: real-game verification + follow-ups)
**Did:** Verified auto-export in real matches and fixed what the game exposed (BUG-037 home-screen misclick, BUG-038 HUD detector, blocker timing → standby blocker 0.05 s, Master-league rank OCR). Dashboard performance (lazy deck pages, hidden-hub dashboard, background sprites, opacity slider). Statistics rework (exact Beta, pooling, meta-adjusted, tie modes, weighted personal records). Unified meta sheet (meta_sources.py: online + in-person + Japan, era/legality weighting). Preferences (weights.py). New Meta and In Person tabs, decklist capture (decklists.py). Published v2.4.0 as a GitHub pre-release.

**Next:** see [[Handoff 2026-10-12]] → Open items (silent-install exit, rebuild installer, manifest update).

## 2026-10-12 — Claude (Dashboard charts overhaul)
**Did:** Replaced the Stats-tab matplotlib Elo / win-rate graphs with an interactive pure-Qt chart (`charts.py`, `SeriesChart`). Added to `release_manifest.txt`.
- **x axis = game / rank change, evenly spaced**, so breaks between sessions no longer squash the data. Days get dotted separators. Day labels are placed newest-first and **dropped when they would collide** (no rotated or overlapping text). Y ticks use a nice-number step sized to the chart height.
- **Auto range (default):** rank = the current climb (walks back until a ≥300 jump such as ladder → Master points, a 3-week break or 60 points). Win rate = last 30 games. Y always auto-fits the visible data (rank clamped ≥0, win rate 0–100 incl. 50%).
- One shared range bar: Auto · Session · 1W · 1M · 3M · All, saved as `dashboard_chart_range` in `.app_settings.json`. Time ranges on the rank chart start from the reading before the window, so the change matches the Today card.
- Hover = crosshair + tooltip (rank: ▲/▼ change, time, league, the game that caused it; win rate: rolling record, game #, opponent, deck, all-time %). Drag = zoom, double-click / right-click = reset, wheel = page scroll. Summary line above each chart describes the visible range.
- Rank: one point per **change** (repeat OCR readings collapsed), dots green/red by direction, league threshold lines (labels de-overlapped). Win rate: rolling last-N (5/10/20/50 picker, `dashboard_winrate_window`, default 10) under the tie rule, dashed all-time line, W/L/T strip along the bottom.
- Headline cards cut from 6 to 4, most useful first: **Current rank** (league, peak), **Win rate** (record, tie rule), **Today / Last session** (record, ±pts, %), **Last 10** (record, form dots, streak). Removed Total/Wins/Losses/Best Elo (now in the subtitles).
- `BattleDatabase.get_battle_timeline()` added. Pre-change copies in `Backups/pre-charts/`.
- Verified offscreen against a copy of the real DB at 1100 and 900 px: auto/hover/all screenshots, drag-zoom, reset, every range, refresh keeps the view.

**Next:** check it on the real PC (fonts are Segoe UI there; offscreen used a fallback). Possible follow-ups: per-deck filter on the charts, and the same chart on the deck pages (they still use matplotlib `MplCanvas`).

## 2026-10-12 — Claude (Win-rate confidence band, chart font)
- Charts use **DejaVu Sans 10 px** again (what the old matplotlib graphs used), loaded from matplotlib's bundled TTF via `charts.chart_font()`; app font if matplotlib is missing. Card values back to 28 px.
- Win-rate chart: solid line = **weighted Beta posterior mean after each game**, shaded band = its **90% likely range** (`CREDIBLE_LEVEL`). Same maths as the deck pages: `battle_weight` (era × league/tournament) → Kish effective n → `win_rate_posterior` under the tie rule, computed with running prefix sums (O(n)). The band narrows as effective games add up. Games older than two expansions count 0, so the earliest stretch stays at the Beta(2,2) prior (wide, 50%), and the tooltip says "not counted". The band can widen slightly when much heavier games arrive (Kish n drops when weights mix). Dashed = rolling last N. Auto = last 100 games.
- `SeriesChart` supports `lo`/`hi` per point (band). `get_battle_timeline()` also returns `my_rank`, `is_tournament`. The Win rate card subtitle shows "est. 66% (53–79)".

## 2026-10-12 — Claude (Deck pin / star / ignore, In Person cleanup)
- The single ★ pin button on deck pages is replaced by three painted toggles (`ui_widgets.DeckFlagButton`, no emoji/glyphs): **Pin** (front of the Decks tabs, `.pinned_decks.json`), **Star** (deck shows as a ★ row in the Meta tab; checkbox renamed "★ Starred decks"), **Ignore** (left out of the headline cards, both charts, Deck Performance list, Recent Battles and Meta rows; the deck keeps its tab, dimmed and sorted last). Star/ignore live in `.deck_flags.json`. On first run `starred` is seeded from the pinned list, since the old star was the pin.
- Animation: press squeezes the icon (0.82, 90 ms), release springs back with OutBack overshoot (340 ms), colour crossfades (200 ms), switching on draws an expanding ring (star adds 6 sparks).
- Toggles apply **in place**: tabs move with `QTabBar.moveTab`, dashboard pieces refresh via `_refresh_dashboard_summary()`, and the Meta tab is marked dirty. The page isn't rebuilt, so the animation finishes. `DeckTabBar` paints a blue dot on pinned tabs and dims ignored ones (the tab stylesheet overrides text colours).
- Ignore doesn't touch the rank chart (it's your ladder rank) or the overlay's today W-L (`session_stats`).
- In Person tab: removed the emoji from the Event finder / Track your homies / Print buttons and the trophy on 1st place in the in-person placings.
- **Gotcha:** the overlay imports `StatsUI` at start and keeps the dashboard alive, so code changes only show after restarting `OverlayUI.py` (the user saw the first charts.py font because of this).

## 2026-10-12 — Claude (Statistics wording pass)
- One phrasing everywhere: **"72%" + "range 54–88%"**, built by `_pct_range()`. Explanations come from `RANGE_EXPLAINED` ("Confidence range (90%): where the true win rate most likely sits. It narrows as you play more games."). No more "likely x–y%", "Bayesian WR" or "95% CI".
- Visible text only shows what isn't elsewhere on the page. Methodology (weighting, effective games, chance >50%, actual record, Limitless benchmark) moved into hovers.
  - Deck page cards: captions are now just the range. Removed the record/actual (in the header), "faced X% of the meta" (it's the META FACED tile) and the "est."/"exp." tags. Verdict says "N% chance" instead of "N% sure".
  - Matchup table: "Likely range" → "Range". The estimate cell hover shows the range and the chance you're favored.
  - Dashboard: Win rate card "27-18 · est. 65%" with details on hover. Rank summary dropped "peak" (in the hover with low and number of changes). Win-rate summary "65% 51–78% · 27-18 · dates", with the legend and stats on hover.
  - Deck Performance rows now use the **same weighted 90% estimate as the deck page** (was the unweighted 95% summary): "72%" over "54–88%", record as subtitle, everything else on hover. Decks whose games are all older-format show "--" / "Older format" with an empty grey bar.
  - Meta tab "Likely range" → "Range". The Limitless/Japan tables' "Raw WR / Bayes WR / 95% CI / P>50" → "Actual / Estimate / Range / Chance >50%". Those tables keep their own 95% maths.

## 2026-10-12 — Claude (Deck Score + Meta view filters)
- **Audit:** "Bayes WR" was genuinely Bayesian (exact Beta-Binomial), but (1) meta W/L were weighted sums larger than the real game counts (Dragapult 7,217 weighted vs 4,847 raw), so ranges were too narrow; (2) games are clustered by pilot; (3) the prior was a fixed Beta(2,2).
- `meta_sources.py`: per-archetype Kish sums + per-pilot records → `eff_games` per row and `pilot_sd` on the sheet. **Build split:** `build_meta_sheet` (network) saves `.meta_store/last_inputs.json`, `rebuild_meta_sheet(use_weights, sources)` re-assembles from cached events only (~0.2 s), and `_assemble(...)` holds the pure maths. Excluded sources still register names/icons, so archetype names stay stable.
- New [[deck_score]] (`deck_score.py`): hierarchical empirical-Bayes Score. Meta tab columns now `# · Deck · Score · Range · Share · Top cut · Record · Win % · Converts · Sources`, sorted by Score. ★ rows show the would-be rank. The deck page "VS THE META" card became **META SCORE** ("Would rank #N of M"), and RANK-WEIGHTED became TOP 5 CHANCE once ranked.
- Meta tab **Data:** All sources / Online / In-person / Japan, plus a **Custom weights** toggle (on by default; off = every event and game counts once, raw records for your games too). Meta tab only; deck pages keep the full weighted sheet. In-person/Japan views have no Score (placings only), and the status line says so.
- Manifest: added `deck_score.py`, `meta_sources.py`, `weights.py`, `decklists.py` (the last three were the handoff's open item 2).
- Real `.meta_cache_limitless_standard.json` rebuilt with the new fields (backup in `Backups/pre-charts/`).

## 2026-10-12 — Claude (Score prior fix + hover formulas)
- The user's Gengar deck (14 games, 11-3) ranked #1 at 61.4 because its prior used the pilot spread (τ = 13 pts). It now uses archetype uncertainty + the fitted deck spread (≈4.2 pts): **48.6 (40–57), would rank #10**, with a 31% top-5 chance. See [[deck_score]].
- New `formulas.py`: every custom rating/weighting shows its formula with the numbers plugged in on hover. Covers the deck page Win rate / Verdict / matchup cells, the dashboard Win rate card, Deck Performance rows, the win-rate chart summary, Meta tab Score (fitted k, θ with its starting value, biggest share × rate terms), Record (event weight + effective games: played → weighted → effective), Share / Top cut / Converts headers and cells, and the Custom weights button. Added to the manifest.

## 2026-10-12 — Claude (Own-games score, ★ highlighting, Bayesian conversion)
- Your decks now get two Scores: **with archetype** (deck strength) and **own games only** (your results, nothing borrowed). Meta tab combo for ★ rows; deck page OWN GAMES SCORE tile; both in the hover with formulas.
- ★ rows: `ui_widgets.MineRowDelegate` paints a purple tint plus a 4 px accent bar (the table stylesheet makes item backgrounds transparent, so `setBackground` wouldn't show). The deck cell gets a purple bold title and a filled "YOUR DECK" badge with "N games · basis". Score text and range bar are in purple.
- Converts column is now the Bayesian conversion (see [[deck_score]]) with its formula on hover.
- The user asked for no hidden-gem detector; it was removed before shipping. Gems should come out of the Score itself.

## 2026-10-12 — Claude (Opponent strength + precision ranking, commit)
- ★ row score/bar use the normal colour scale (by value, ranked or not); only the row tint/badge is purple.
- Opponent strength: `deck_score.adjust_personal` (ladder gap on the log-odds scale + evidence factor), new Preferences group **Opponent strength** (`ladder_evidence` 0.5, `ladder_gap` 4 pts, `tournament_evidence` 1.0, `rank_margin` 15 pts). In-person Day 2 → Top 32 enters θ through the fitted logit link β (≈ 0.6 on current data = weak link; reported honestly in hovers).
- Ranking rule per the user: effective games ≥ (1.645 × 0.5 / margin)² (30 at ±15 pts). Raw-count thresholds removed (`MY_MIN_GAMES` is gone). Same rule for meta decks (plus the Min games filter).
- Handoff rewritten; committed locally on `main`.

## 2026-10-12 — Claude (Meta order fix)
- Unranked rows (below the effective-games threshold) were sorted after every ranked row by share, so Gengar 46.1 appeared below decks scoring 41.9. Now every row with a Score is in Score order (unranked rows just show no rank number); placings-only rows come last, by share.

## 2026-10-12 — Claude (Predicted ranks with ranges)
- Every deck now gets a simulated rank position: per draw, position = 1 + ranked decks scoring higher. `rank` = point estimate at its Score, `rank_low`/`rank_high` = 5th/95th percentile, `ranked` = firm (effective games >= threshold). Below the threshold the # column shows "~28" (predicted) with the range on hover; the deck page says "Predicted ~#28 (#1–#62) of 64". Ranked decks show their rank range too. Gengar Testing: ~#28, 90% range #1–#62 (7 of 30 effective games).

## 2026-10-12 — Claude (Predicted scores marked *)
- Scores below the firm-rank threshold show italic with an asterisk ("46.1*" in the Meta tab, "46*" on the deck page META SCORE card and OWN GAMES SCORE tile). The hover starts with "* Predicted score · range 38–55% · 7.0 of 30 effective games for a firm rank" (`StatsWindow._predicted_note`).

## 2026-10-12 — Claude (Low-confidence marker, Meta tab only)
- Reverted the italic/asterisk formatting on the deck page (META SCORE card, OWN GAMES SCORE tile are plain again). Meta tab only: a single asterisk (no italics) when the Score's 90% range is wider than +/- 6.5 pts (`StatsWindow.SCORE_FLAG_PTS`; meta ranges are capped near +/- 7 by the prior, so this means "still mostly the starting assumption"). Hover header: "* Low confidence · 90% range 38–55% (+/- 8.6 pts, wider than +/- 6.5)". Flags 20 of 82 rows on current data. Rank column keeps "~" for predicted ranks.

## 2026-10-12 — Claude (Installer rebuild + hidden monitor)
- Rebuilt the installer (smoke test all OK). Silent install exit 0.
- Found and fixed: (1) the installer deleted the dev checkout's auto-start value when auto-start was unticked (restored the user's value; guarded with `RunValueIsOurs`); (2) the headless monitor blocked on the username dialog before the game opened (now deferred to game detection); (3) the idle process scan cost 33% of a core (`psutil.process_iter` ~3 s per scan) → Toolhelp32 snapshot, 16 ms, idle now ~0.3%.
- Verified: installed hidden monitor (no window, BelowNormal, "Waiting for Pokemon TCG Live..."), and the user's real auto-start command exits cleanly while the manual monitor runs. Details in [[Handoff 2026-10-12]].

## 2026-10-12 — Claude (Release v2.5.0)
- `version.py` → 2.5.0 (UI shows 2.5; the meta User-Agent now reads the version). README + manifest point to the new `RELEASE_NOTES_v2.5.md`.
- Installer rebuilt as `PokemonTCGLiveMonitor-2.5.0-Setup.exe` (smoke test 0 failures). Install-tested: silent install exit 0, the user's auto-start value preserved, hidden monitor logs "Monitor v2.5 starting … Waiting for Pokemon TCG Live...".
- Tagged `v2.5.0`, pushed `main` + tag, published the GitHub release (Latest) with the installer and `.sha256`. The v2.4.0 pre-release was left as is.
