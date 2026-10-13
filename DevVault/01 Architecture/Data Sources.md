---
tags: [architecture, data]
updated: 2026-10-13
---
# Data sources

Every external source the meta data could come from, which ones are used and why. The rule: **each event is counted once.** Many sites republish the same tournaments, and adding a mirror double-counts those events. Built by `meta_sources.py` (see [[Data Model]] for the cache files).

## Used
| Source | What it gives | Speed / limits | Notes |
|---|---|---|---|
| **play.limitlesstcg.com API** (`/tournaments`, `/standings`, `/pairings`) | Online events: every player's deck, W-L-T, **full decklist**, every pairing (matchups) | ~0.1–0.4 s per call. **Rate limit 50 requests / 5 min without a key** (`RateLimit: "50-in-5min"; r=…; t=…`) | All 32+ player Standard events in the format window (~170 a month, ~870 since Chaos Rising). 2 calls per event, cached forever (`online_v3_<id>`). `_api_get` + `_ApiThrottle` read the header and wait/stop; the full window fills in over a few refreshes (current format, biggest events first). Optional key: `.app_settings.json` `limitless_api_key` or env `LIMITLESS_API_KEY` (header `X-Access-Key`). |
| **limitlesstcg.com** in-person (`/tournaments?format=standard`, `/tournaments/<id>`, `/statistics`) | Regionals / ICs / Worlds: deck shares, Day 2 placings, legal set range | Fast HTML, no limit seen | Day 2 placings → Top cut / Converts |
| **limitlesstcg.com `/tournaments/<id>/decklists`** | **Every published Day 2 decklist of an event in one page** (Louisville: 547 lists, 21 MB, 1.7 s) | One request per event | Parsed with one regex pass (0.08 s), summarized per archetype (`inperson_lists_<id>`). Feeds card usage. |
| **labs.limitlesstcg.com** | In-person pairings for every round with nearly every player's deck → full-field records and matchups | ~8 ms parse per 3 MB page | 11 of 12 recent events (Indonesia PBL isn't on Labs). |
| **limitlesstcg.com/tournaments/jp** | Japanese City Leagues: top 16 by deck icons, city, shop | `show=500` per page (`show=1000` returns the default 25), `page=` works | ~230 events since the JP season restarted 2026-09-26. Mirrors the official Players Club results. |
| **tools.trainerhill.com** (BFF API) | Meta share trend over time | 4–7 s per query, occasional 502 | Trend view only (it's built on Limitless data, so it never feeds the sheet). |

## Checked and not used (would double-count or not reliable)
| Source | Why not |
|---|---|
| RK9 pairings | Same in-person events as Labs; only Day 2 rounds are unbiased. Labs is better. |
| pokekameshi.com (data lab, tier list, winner posts) | City League numbers are the same official top-16 lists Limitless JP carries. Its own "voluntary tournament" data is off-season only, top 4/8 and form-submitted. Scraping was fragile (hard-coded slugs, AI translation). The old `japan_data.py` scraper was removed on 2026-10-13. |
| pokemoncard.io weekly JP posts | Winners only, from X posts of the same City Leagues. |
| players.pokemon-card.com (official JP) | The primary source behind Limitless JP. No public API. Linked from the Japan tab. |
| PTCG Legends | Mostly retro formats; no API. |
| Apify / other Limitless scrapers | Copies of Limitless. |
| Limitless `/games/.../decks` (deck rules) | Needs an API key; not needed (the API already assigns decks). |

## Weighting reminders
Event weights (source, format age, size) are in [[deck_score]] and Preferences. Card usage weights each decklist by format age and source only (no size factor). Japan placings never mix into win rates.
