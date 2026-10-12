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
| 6622–7128 | `load_stats`, Elo/WR graphs, deck list, recent battles (UTC display, BUG-004) |
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
