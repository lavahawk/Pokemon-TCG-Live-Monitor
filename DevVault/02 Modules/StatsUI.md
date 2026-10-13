---
tags: [module]
file: StatsUI.py
lines: 8243
---
# StatsUI.py: dashboard (and a lot more)

8.2k lines in one file. It contains: helpers for sprites and TrainerHill Dash trees, `LimitlessCheckInAlert`, `ReplayWebPage`, **[[Limitless Dashboard Manager]]**, `MplCanvas`, `DeckIconPickerDialog`, `MetaFetcher` (Limitless API + TrainerHill), `JapanFetcher`, and `StatsWindow`.

## Line map (2026-10-11)
| Range | Content |
|---|---|
| 78–122 | `PageScrollArea` (wheel always scrolls page) |
| 125–155 | stale `JP_DECK_TRANSLATION` copy (unused) |
| 203–345 | sprite cache: pokesprite → PokeAPI fallback (SEC-08) |
| 436–577 | check-in alert popup |
| 642–666 | `ReplayWebPage.chooseFiles` auto-answers file picker |
| 668–1751 | `LimitlessDashboardManager` (BUG-001, 017, SEC-03/04/05) |
| 1801–2258 | deck icon picker dialog |
| 2275–2645 | `MetaFetcher`: Limitless `/api/tournaments` (15 latest) → standings aggregate → per-deck page W/L scrape (8 threads) → sprites; TrainerHill via `/_dash-update-component` |
| 2672–3190 | `StatsWindow` shell: frameless, edge resize, opacity, geometry persistence, protected-interaction focus logic |
| 3192–4375 | Stats tab + per-deck dashboards (Bayes, Wilson, rank-weighted, meta benchmark, matchups) |
| 4376–4695 | Replay tab (embedded ptcglreplay + JS file injection) |
| 4696–4948 | Advanced tab: console toggle, OCR test (BUG-015), parser settings/API key, autorun, battle DB editor, close app |
| 5267–5890 | Limitless meta, Limitless dashboard, TrainerHill, Japan tabs |
| 5891–5965 | PokeData embedded site |
| 6305–6360 | `close_application` (terminates monitor by PID file) |
| 6622–7128 | `load_stats`, headline cards, rank/win-rate charts (`charts.SeriesChart`, since 2026-10-12), deck list, recent battles |
| 7137–7346 | Playwright replay fallback (BUG-033) |
| 7390–7620 | Battle management table editing/deleting |
| 7621–8228 | stylesheet |

## Behaviour notes
- Rendered offscreen with the real DB (below). Totals 39 / 48.7% / Elo 260 (inflated by duplicates, see [[Data Integrity Audit]]).
  ![[shot_stats.png|600]]
- matplotlib `Qt5Agg` with only PySide6 installed: **verified OK** (matplotlib 3.8.2 and 3.11 both resolve QT_API=PySide6).
- Refresh: every 15 s, paused while focused (BUG-028).

## Refactor target
Split into `ui/stats_window.py`, `ui/tabs/*.py`, `integrations/limitless.py`, `meta/fetchers.py`, `ui/widgets.py`. Overlay should import only `integrations/limitless.py`.
Related: BUG-001, 004, 015, 017, 022, 028, 033, SEC-03/04/05/08.

## Base archetype (2026-10-12)
Deck page header: "Base archetype" line edit under the record (`_create_base_archetype_field`), autocompleting Limitless archetype names (contains match). Placeholder shows the automatic match ("Auto: X") or "No match". Enter / pick commits; an unknown name turns the border red; clearing it returns to automatic matching. Stored in `.deck_archetypes.json` via `deck_analytics.set_deck_archetype`; `match_meta_row` checks it first, so the matched row, icons, Limitless link, matchups vs Limitless and the Score's `mirror_id` all follow. `_apply_base_archetype` rebuilds that deck's analysis and page in place; the score cache key includes `deck_archetypes_signature()`.

## Matrix deck picker, Overlay prefs (2026-10-12)
- Meta → Matchups: **Decks…** button (only on that view) opens `MatrixDeckPicker`: your decks (all non-ignored, with game counts) and archetypes with online records (searchable, Top N / None). OK saves `matrix_archetypes` / `matrix_my_decks` in `.app_settings.json`; a pick equal to the automatic default saves null, so it keeps following Matrix size / ★. "Reset to automatic" clears both. The button reads "Decks: custom", and the size spin is disabled while archetypes are custom. `_meta_matrix_args` now carries every one of your decks; `_matrix_selection` decides what's shown.
- **Fixed:** the mirror "—" used `i == j`, but your ★ rows are prepended, so with starred decks the dashes sat on the wrong cells and the real mirror cells showed numbers. Now compared by row id.
- Advanced → **Preferences · Overlay** card (`_create_overlay_prefs_card`): show max Elo, offer W-L reset at game start. Saved on toggle (`_save_app_setting`).

## Meta tab: Trend view, controls (2026-10-12 night)
- **Trend** (third view, after Archetypes / Matchups): TrainerHill's Meta Trend drawn natively (`charts.TrendChart`), data from `trainerhill_trend.py`. Controls: Period 2W / 1M / 3M / This set (EN expansion date from the sheet), Online / In-person (TrainerHill `play` / `labs`), Min players, % Share / Count, Lines / Stacked, 7-day smoothing, Chart / Table, TrainerHill ↗. Left list: search, Top 5 / 10 / 16 / Clear, checkable archetypes with colour swatches (the legend); hovering a ticked row highlights its line. Table: players, share, last 7 days, change vs the 7 days before (↑ / ↓ beyond ±1 pt). Fetches run on `CallFetcher` (QThread) with a token so stale results are dropped; ticking decks is debounced 350 ms. Loaded the first time the view opens. State is saved under `meta_trend`.
- Colours: `charts.SERIES_COLORS`, the dataviz reference dark palette, validated on #0B0F17 (adjacent CVD ΔE ≥ 8.4, normal ≥ 19.3, contrast ≥ 3:1). A deck keeps its slot while ticked (`_trend_assign_slots`). Slots 9-16 reuse the hues with dashed lines or hatched fills; the maximum is 16 decks.
- Removed the "Japan-only decks" checkbox (the Japan data view shows those decks; `include_jp` = source is Japan). "★ Starred decks" became the **Show my decks** toggle next to Custom weights (same `eloScaleBtn` style, still `self.meta_include_mine`); the "scored with archetype / own games" combo sits after it and hides with it.
- Texts updated: in-person has W/L + matchups; "no Score" now only for Japan; the status line shows "N in-person (M with results)".

## 2026-10-12 late
- The "Limitless TCG Live Meta" tab is gone (Meta tab replaces it). Meta data loads via the startup cache + `_refresh_decks_meta` / `_on_decks_meta_data`.
- `range_domain(values, pad, min_span, step)` and `RangeBar(..., domain=(lo, hi) | "auto")` for zoomed error bars. The Meta table uses one shared par ±8 axis; deck cards auto-zoom.
- The Meta Score cell shows "score ±half-range".

## TrainerHill tab (2026-10-12 late)
Embedded tools.trainerhill.com (`create_trainerhill_tab`, `_ensure_trainerhill_view`, `open_trainerhill_tool(path)`, `ToolsPage`). See Session Log. The Meta Trend view's data still comes from `trainerhill_trend.py` (their API), drawn natively.
