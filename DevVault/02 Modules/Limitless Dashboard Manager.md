---
tags: [module, integration]
file: StatsUI.py (L668–1751)
---
# LimitlessDashboardManager

Singleton (`get_limitless_dashboard_manager()`) attached to the QApplication, created by the overlay at startup. It owns a persistent QtWebEngine profile in `.limitless_web_profile/` (login cookies), a hidden **background page** (dashboard), a hidden **chat page** (active match), and optionally the visible dashboard tab's page.

## Intended loop
- `poll_timer` 60 s → `poll_for_checkin` → `_checkin_scan_js` → `{loggedIn, inTournament, activeMatchUrl, candidates[]}`.
- New check-in candidate → auto-click via injected JS (or show the alert if auto is off).
- `activeMatchUrl` → chat page → `chat_poll_timer` 3 s → `_chat_extract_js` (heuristic DOM walk, timestamps, sender detection, match check-in button, "Open as image").
- `_publish_chat_state` → overlay chat window + `.chat_capture.json` + `.in_tournament`.
- While in a tournament: `tournament_poll_timer` 10 s reloads the dashboard.
- Auto "Open as image" opens the opponent's decklist in the default browser once per match.

## What actually happens
See [[Process Map]] §5. **BUG-001** (init lines inside `_tournament_poll`) means `delayed_poll_timer`/`chat_poll_timer` are missing and the profile isn't created at startup, so polling never starts. **BUG-017** keeps `.in_tournament` true with an empty opponent.

## Security
SEC-03 (clipboard JS access), SEC-04 (open scraped URLs), SEC-05 (unchecked match URL). Auto check-in clicks the first visible element whose text matches `/check[\s-]?in/`, which is acceptable but brittle.
