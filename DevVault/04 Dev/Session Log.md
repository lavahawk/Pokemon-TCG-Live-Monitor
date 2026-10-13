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

## 2026-10-12 — Claude (Restart on v2.5 code)
- Stopped the 04:14 console monitor + overlay (pre-fix code, old psutil scan) and a leftover scratch `time_decks.py` from an earlier session (running since 02:44). Relaunched with `Run_TCGLiveMonitor_Command_Prompt.bat`: "Monitor v2.5 starting (pid 74048, console)", overlay started, auto-export watcher started, menu OCR rank=1513.
- Found: the old monitor's 17:55 startup OCR stored rank **402** (`rank_history` id 134) between two 1513 readings, so the rank chart shows a fake drop. Not deleted yet (user's call). Possible follow-up: reject startup readings that jump >300 from the last reading in the same league within a few hours.

## 2026-10-12 — Claude (Suspect rank re-check)
- User confirmed the startup rank 402 was wrong. Deleted `rank_history` id 134 (DB backup in `Backups/`).
- Cause: a **stable** misread. 402 passed `read_rank_confirmed`'s three identical reads (jump > 100), 56 s after game launch, probably a menu still loading. The old process had the padded Master-league read (it read 1490/1501/1513 fine overnight), so it wasn't the pre-fix code.
- Fix in `detect_menu_stats`: a confirmed reading more than `SUSPECT_RANK_JUMP` (300) from `.last_rank` isn't stored. It saves the rank crop to `Logs/rank_suspect_<rank>_<time>.png`, waits `SUSPECT_RECHECK_S` (8 s) and reads again. It is accepted only if the same value comes back (e.g. a season reset); a reading near the old rank is accepted normally. Tested with a fake detector: misread then real → 1513, reset 30,30 → 30, misread then nothing → nothing stored, normal → stored.
- Not loaded yet: the user was in a battle, so the monitor restart is pending.

## 2026-10-12 — Claude (Base archetype + Opponent deck card)
- **Base archetype:** custom deck names (e.g. "Pult Hammers NAIC 2026") can now name the Limitless archetype they are a version of. The deck page field has autocomplete; the mapping lives in `.deck_archetypes.json` and `match_meta_row` checks it first. Verified on a scratch copy of the app: Pult Hammers had no match (Score 43.0 from the typical-deck prior). Set to Dragapult Dusknoir → `mirror_id` dragapult dusknoir, Score 42.0, Limitless ↗ button appears. The user's real decks have no mapping yet.
- **Opponent deck card** (new `deck_confirm.py` without Qt, `deck_popup.py` with Qt, both in the manifest): after each saved battle the overlay shows the AI's pick (fades once back on the main menu, click to fix), or asks for the deck when there's no AI pick, with autocomplete, an unknown-name confirm (new deck / Other), a chime and a check animation. Details in [[OverlayUI]] and [[AIParseBattleLog]]. Rendered offscreen in all states. Not yet seen live.
- Fixed in passing: the local-mode opponent prompt was invisible under the monitor (stdout captured) and blocked the parser up to 180 s. `deck_source` said AI after a failed AI parse.
- **Gotcha (tooling):** in this environment, `\n` inside a Bash heredoc reaches Python as a real newline. Build escape sequences with `chr(92)` or use the Edit tool.
- **Live check 19:49:** restarted the monitor after battle #65 (pid 79656, overlay restarted). The parser (new code) had written the request; the new overlay showed the card for #65 (Dragapult Blaziken, AI), the startup menu read 5 s later set `.menu_seen`, and the card faded and was marked handled. No overlay errors. The suspect-rank re-check is now loaded too (startup rank 1487 = after-battle 1487).

## 2026-10-12 — Claude (Session reset prompt, max Elo toggle, matrix picker)
- **New-session reset prompt:** the monitor marks `Logs/.game_session`, and the overlay shows a fading "New session · Reset? (W-L)" popup above the mini GUI (10 s, hover keeps it). Not shown at 0-0. Live-verified at 20:02 after the restart: "session reset prompt (11-6)". See [[OverlayUI]].
- **Max Elo toggle:** Advanced → Preferences · Overlay. The pill shrinks 165 → 110 px without `Max:`. Verified offscreen.
- **Matrix picker:** Meta → Matchups → Decks… chooses the archetypes and which of your decks are in the matrix. It also fixes misplaced mirror cells when ★ rows were shown. Verified on a scratch copy: automatic 16×14 with 14 correct mirrors; custom 2 decks + 5 archetypes → 7×5, 5 correct mirrors. See [[StatsUI]].
- Monitor restarted 20:02 with all of today's evening code loaded. Still uncommitted.
- **Fix (user report: prompt appeared way too high):** at 20:02 the prompt opened 40 ms before the overlay's first `follow_game_window` move, so it was placed against the overlay's pre-move position and never followed. Anchored popups (session prompt, deck card) now wait for `_overlay_placed`, and `_position_reset_popup` re-anchors the Reset? popup on every overlay move. Re-tested live at 20:04: pos 20:04:01.172 → prompt 20:04:02.182.

## 2026-10-12 — Claude (In-person records, Trend view, Meta controls)
- **Why in-person had no Score / Record / Win %:** limitlesstcg.com in-person pages only publish placings and decks for Day 2 players. We only scraped shares + Day 2 placings, so there was nothing to compute a record from.
- First tried RK9 pairings (Day 2 rounds only, since Day 1 results of Day 2 players are survivor-biased). The user pointed to **Limitless Labs**, which is much better: its pairings show nearly every player's deck (Louisville round 1: 2,918 of 2,942), so every round of the whole field is usable with no bias. The RK9 code was dropped before shipping.
- `meta_sources`: `list_labs` (index, 6 h), `match_labs_event` (start date ±3 days + fuzzy place word; 11/12 matched, the Indonesia PBL isn't on Labs), `fetch_labs_results` (decks page → slug/name/icons; every round's pairings parsed with regexes, about 8 ms per 3 MB page; archetypes sharing icons, such as Basic Box / Clefairy Ogerpon and Metagross / Steven's Metagross, resolved via their deck pages). Aggregated per event: records, matchups, per-player records. `_assemble` adds them weighted like any in-person event. **Verified:** Louisville 11,402 games, 48 unknown; Dragapult Dusknoir 352-405-93 vs Labs' own 353-406-93; the Dusknoir vs Dragapult matchup equals Labs' 70-89-16 exactly.
- Labs pages declare no charset, so they're decoded as UTF-8 explicitly (requests used Latin-1, and the en dash broke the date regex).
- Real sheet rebuilt (backup `Backups/pre-charts/meta_cache_before_labs.json`): 8 of 9 in-person events have results; Dragapult 31,659 games (26,802 in-person). In-person view: 54 archetypes ranked (none before).
- **Trend view** + `trainerhill_trend.py` + `charts.TrendChart`. The backend needs an anonymous BFF session (GET /bff/session → cookie + csrf), and `meta_trend` sometimes returns a 502 (retried). Queries take 4-7 s, so they run in the background.
- Meta controls: Japan-only checkbox removed; Show my decks toggle.
- Note: the user's tie rule is **ties as losses**, which is why most Scores sit below 50.
- Not yet loaded in the running overlay (the user was mid-battle). Uncommitted.
## 2026-10-12 — Claude (Meta row accuracy: record + top cut)
- User asked whether the Dragapult row was accurate. Two display problems found:
  1. **Record** showed event-WEIGHTED sums (42,460-35,804-13,378 = 91,643) for 31,659 real games. That was harmless while records were mostly online (weight ~1); with Labs in-person games weighted ~1.75 × size (up to ~5x) it inflated about 3x. Rows now carry `raw_wins/raw_losses/raw_ties` (sum = `raw_games`), and the Record column shows them; the weighted record is in the hover (Win % and Score still use it). Dragapult: 14,868-12,554-4,237.
  2. **Top cut vs Share** compared different fields: Share was the English field (`share_en`), but `top_share` mixed in Japanese City League placings (Dragapult 8.3%, which looked like under-conversion, contradicting Converts 1.24x). New `top_share_en` (in-person only) is used whenever Share is `share_en`; the Japan view keeps `top_share`. Dragapult: 24.6%.
- Checked and correct: Win % (= weighted W / (W+L+T) under ties-as-losses), the Sources hover (events this deck appeared in), Converts.
- Sheet rewritten; overlay restarted 20:44 (monitor kept running, so no new-session prompt).

## 2026-10-12 — Claude (Weights never add games; par)
- **User rule:** weighting must change how much each match counts, never how many matches there are.
- Audit: your own games were already right (`weighted_record`, Kish-normalised). The Score was nearly right, because it rescaled weighted sums to effective games before any maths. The sheet itself stored weighted **sums**, though (Dragapult 91,643 "games" from 31,659), and other readers (matrix ranges and the like) took them as games.
- **Fix (meta_sources):** `wins/losses/ties` = weighted proportions × real games (sum = `raw_games`); matchup cells the same with real per-cell counts (`mraw`). `record_basis: "real_games"` on the sheet. Effective games (Kish ÷ design effect) ≤ real games drive all uncertainty. Invariants checked: no row's weighted record differs from its games, no matchup cell exceeds them, no effective count exceeds real.
- **Par:** with ties-as-losses an even contest scores (1 − T)/2 + T × tie share, not 50%. Field tie rate 11.8% → **par 44.1%**. `deck_analytics.tie_par/record_par` (tie rate shrunk with a 4-game prior toward 12%); `win_rate_posterior` centres its prior on par and `p_above_even` = P(> par), with a `par` key. Score: mirror = par, `p_above_even` vs par, `info["par"]`. RangeBar tick, matrix red/green, verdicts and hovers all use par; `_par_text` prints "50%" or "par 44.1%". In half / ignore modes, par is exactly 50%, so nothing changes there.
- Sanity: Scores moved ≤ 1 pt (Dragapult 48.5 → 47.6, from its 13.8% mirror share now worth par); share-weighted field average 43.2 vs par 44.1 (small-sample decks shrink toward the typical-archetype prior mu 38.5%). 9-9-2 → exactly 50% vs par; 10-10-0 → 53%; 30-20 → 92%. Gengar 42.2 (32-53), own games 45.0; Pult Hammers 39.1 (no base archetype set yet).

## 2026-10-12 — Claude (Zoomed ranges, Score ±, wording, Limitless tab removed)
- **Cut-off word:** the Trend view's "TrainerHill ↗" button (`limitlessBtn` style taller than the 24 px row) → `eloScaleBtn`. Rendering at the user's real window (1127×668, DPR 1.5) also showed that pinning the Range column clipped long deck names; widths rebalanced (Range 150 px).
- **Range zoom:** `range_domain()` + `RangeBar(domain=...)`: zoomed axis, 5-point ticks, chevrons when a range runs past the edge, axis-end labels. Meta table: one shared axis at par ±8 points (36-52 at par 44.1), about 6x the old 0-100. The Range column is pinned (cell widgets have no content width, so ResizeToContents shrank it). Deck cards: `domain="auto"` around range + par + benchmark (e.g. Win rate 35-80, Meta Score 25-60).
- **Score:** shown as "47.9 ±0.6" (half the 90% range). The Record header lost its ⚖ (it shows real games now).
- **"Effective games" wording:** the user asked whether Dragapult really has 20k games. Real: 31,825 player-games (26,802 in-person from ~3,700 player records, 5,023 online); about 21% are mirrors counted once per player, so about 28k distinct matches. 22,824 was the effective sample size, which is not data. It's now called "evidence (effective sample size)", only in hovers and formulas, with an explanation. Visible text shows real games only (★ rows: "21 games · with archetype").
- **Removed the "Limitless TCG Live Meta" tab:** the Meta tab covers it (same sheet, plus an In-person view); its only unique part was the Pocket format (not PTCGL). Deleted `create_limitless_tab`, `_create_in_person_view`, `_populate_in_person`, `_on_limitless_format_changed`, `_fetch_limitless_data`, `_on_limitless_data`, `_on_limitless_error`. Preferences "apply" and Meta ↻ Refresh now use `_on_decks_meta_data`. MetaFetcher still supports `limitless_pocket` (unused).

## 2026-10-12 — Claude (TrainerHill tab → embedded tools.trainerhill.com)
- Replaced the TrainerHill tab (scraped www.trainerhill.com Dash callbacks into a table) with TrainerHill's tools site embedded in a QWebEngineView. Native toolbar: ◀ ▶ ↻, a Tool picker (Home + 11 dashboards: Meta Trend, Breakdown, Tier List, Meta Matchups, Deck Profile / Evolution / Diff, Card Usage / Trend / Matchups, Bracket) that follows navigation, a load status, and Open in browser.
- Own persistent profile `.trainerhill_web_profile/` (gitignored). A DocumentCreation script sets `localStorage["theme-preference"]="dark"` only when unset, so the site starts dark and the user's own Appearance choice sticks. `ToolsPage` keeps navigation on trainerhill.com (other links, including ads, open in the system browser) and loads target=_blank in place. Their Download / Share exports save to ~/Downloads. Built lazily on first open; the last URL is restored (`trainerhill_url` in `.app_settings.json`). Meta → Trend's "TrainerHill ↗" now opens Meta Trend in this tab (`open_trainerhill_tool`).
- Removed: MetaFetcher's `trainerhill` source and its 5 Dash helpers, `TRAINERHILL_BASE_URL`, the old tab handlers.
- Tested offscreen at the user's window size: loads dark (`true dark`), the picker reaches Tier List, Back returns to Home.
- `.gitignore`: also `.deck_flags.json`, `.deck_archetypes.json` (the user has mapped "Kellers Pult Baltimore" → Dragapult).

## 2026-10-12 — Claude (Multiple decklists, importing results, JapanFetcher regression)
- **Decklists:** PTCGL's export doesn't name the deck, so each capture was filed under the deck last OCR'd on the main menu and overwrote the previous list (the user's earlier exports are lost; only the 21:35 list survived). `decklists.py` now keeps a list of lists keyed by card content (`list_id`: same cards in any order = same list; re-export only refreshes it), auto-named from the cards (`auto_name`: main rule-box Pokémon + partner, e.g. "Gengar ex / Mega Gengar ex"), with `rename_decklist` / `delete_decklist`. The old `by_deck` format is converted on read. In Person: the dropdown lists them all (name · cards · date), with Rename / Delete; a 2 s mtime poll picks up new exports while the tab is open and selects the newest. Monitor log: "Decklist saved/updated".
- **Import your results** (Advanced): deck (editable, autocomplete), date, Ladder / Tournament, W/L/T or win rate × games → Fill, weight per game (defaults from Preferences: Master for ladder, tournament weight for tournaments), note. `WeightScale` paints the current league / tournament weights on a log axis with a marker for the chosen weight. The import table supports Remove.
  - Storage: one battles row per game, `deck_source='Import'`, new columns `weight` (explicit per-game weight, × the era factor in `battle_weight`) and `import_id`. Opponent `(imported result)`.
  - Counted in deck usage, deck pages, Deck Performance and the Score (tournament imports count as tournament evidence). Excluded from session W-L (overlay), the timeline / charts, Recent Battles, deck recent / history and matchups (`_my_deck_meta_rows` skips them, `get_deck_matchups` filters them).
  - Verified on a DB copy: Gengar 22 → 38 games, Score 43.4 → 47.6 (evidence 11 → 25), today's W-L / recent / timeline unchanged, no matchup row; Remove restores everything exactly.
- **Regression found and fixed (mine):** the TrainerHill-tab patch removed MetaFetcher's last method by deleting up to the next `def`, which also removed the `class JapanFetcher(QThread):` header. JapanFetcher's `__init__` / `run` merged into MetaFetcher, so every meta refresh since the 21:34 reload loaded Japan data as the Limitless sheet (in memory only; the sheet file was untouched). Header restored; audited every class and method against HEAD (only intended removals). **Lesson:** never delete methods by "up to next def" without checking the class boundary; diff class/method sets with ast after such edits.
- The monitor caps overlay restarts at 5 (`overlay_starts`): tonight's reloads hit it, so the monitor itself was restarted at 21:46.

## 2026-10-12 — Claude (Spin box arrows)
- The spin-box arrows were painted as white squares: `SPIN_STYLE` used the CSS border-triangle trick (zero-size box with coloured borders), which Qt style sheets don't support. `_arrow_icon()` writes small chevron SVGs to `.ui_cache/` (gitignored; qsvg plugin ships with PySide6) and the style uses `image: url(...)`. The same chevron now appears on `metaCombo` drop-downs and the import date box. Disabled spin boxes hide their arrows.

## 2026-10-13 — Claude (Data sources, card usage, open items)
**Committed:** `32795fb` (the 2026-10-12 evening batch), `02c284c` (data + UI), `602ff38` (opponent deck from cards).
- **Data source survey** → new [[Data Sources]] note: what's used, speed and limits, and the mirrors left out because they'd double-count (RK9, pokekameshi, pokemoncard.io, TrainerHill for the sheet, PTCG Legends).
- **Coverage:** the sheet used only the newest **80 online events (~12 days)** and the newest **100 City Leagues**, while its window starts at Chaos Rising (2026-05-22). Now: every 32+ player online event in the window (~870) and every City League (~230, all since the JP season restarted 2026-09-26).
- **Limitless API rate limit found:** 50 requests / 5 min without a key (`RateLimit` header). The first full build got 429s and only 62 events. Added `_api_get` + `_ApiThrottle` (waits within the budget, else stops; the rest loads on later hourly refreshes; current format and biggest events first), dropped the `/details` call, reuse v2 caches' matchups, an optional API key (Advanced → Meta Data). Backfilled the cache in the background (`scratchpad/backfill.py`).
- **Card usage:** online standings carry every player's decklist; in-person Day 2 lists come from one bulk page per event (`/tournaments/<id>/decklists`). Sheet rows get `lists` + `cards` (incl %, avg copies, per list). New **Meta → Cards** view compares an archetype's typical list with your PTCGL exports (`card_usage.py`).
- **Opponent deck from revealed cards** (see [[AIParseBattleLog]]): 9 of 54 stored AI labels contradict the opponent's own cards (some name the user's own deck); the cross-check catches all 9.
- **Japan Data tab** rebuilt on Limitless City Leagues (`meta_sources.japan_view`); `japan_data.py` (pokekameshi scraper) removed.
- **Open items done:** deck-page win-rate chart → `SeriesChart` (now weighted like the card), dashboard win-rate deck filter, overlay today W-L skips ignored decks, console detection without `psutil.process_iter`, BUG-040 closed (13/13 live reads).
- **Perf:** `_key` memoized (rebuild 2.9 → 1.2 s at 220 events); alternative Meta views build on a `CallFetcher` thread.
- **Bug caught by the new tests:** `card_usage.compare` treated "no list" as an empty list (every core card red).
- Tests: `test_card_usage.py` 8/8, `test_rank_weighted.py` pass; every manifest module imports offscreen; Meta → Cards, Japan, deck page and dashboard rendered offscreen at 1127×668.
- **Final build** after the backfill (804 events in 80 min, 0 failures): 849 online + 9 in-person + 232 Japan events, 590k real games (was 178k), 95,559 decklists, build 4.3 s from cache. Shares now reflect the whole window (Dragapult 13.8% → 9.4%). Installed as `.meta_cache_limitless_standard.json` (old one in `Backups/`). Local-mode card picks need the deck's own Pokémon to be seen to count as CARDS (else GUESS).
