# Japan Data — pokekameshi.com Deep Analysis (v2)

> **Goal:** Pull Japanese meta insights from [pokekameshi.com](https://pokekameshi.com) into the app under a single **"Japan Data"** umbrella, so we can compare against our own tracked data (win rates, top decks, tournament detection). This is a **deep, full-site** analysis covering the data lab documents, translation, consolidation, and filtering.

---

## 1. What the site is

**ポケカ飯 ("Pokéka Meshi" / "Pokémon Card Meal")** is a Japanese fan site (WordPress) run by a competitive player who is a member of **ポケカデータラボ (Pokeca Data Lab)** — a data-analysis collective. The site aggregates **winning/placing deck recipes** from Japanese tournaments: City League (シティリーグ), Champions League (CL), PJCS, and community/independent tournaments (自主大会, ジムババトル, スクランブルバトル).

It is one of the best sources for **JP-exclusive meta** — formats and decks that haven't reached the West yet. This is exactly the "Japan data" we want to compare against our own battle history.

---

## 2. Full site structure (from sitemap crawl)

The site is WordPress with **4 post sitemaps** (`post-sitemap.xml` … `post-sitemap4.xml`), a category sitemap, and a misc sitemap. It has **~1,200+ articles** spanning 2020 → 2026-08-17.

### 2.1 Top-level navigation
| Nav label (JP) | Meaning | URL |
|---|---|---|
| 新着記事 | New articles | `/` (paginated `/page/N/`) |
| デッキ一覧 | Deck list (archetype index) | `/category/archetype/` |
| PTCGL | PTCG Live articles | `/category/pokekainfo/ptcgo/` |
| ポケカお役立ち | Useful info / tools | `/category/pokekainfo/pokemoncard-useful/` |
| シティリーグ | City League results | `/category/cityleague/` |
| SiteMap | Full sitemap | `/sitemap/` |
| DeckWriter | Deck-code → article tool | `/deckwriter/` |

### 2.2 Content categories (from `category-sitemap.xml`)
| Category | Meaning | URL |
|---|---|---|
| デッキまとめ | Deck roundups (winning decks) | `/category/tiertop/` |
| カードリスト | Card list / new-card reviews (S/A/B/C ranks) | `/category/pokekainfo/pokemoncardlist/` |
| 優勝デッキまとめ | Winning-deck roundups | `/category/pokemoncard-windeckrecipe/` |
| シティリーグ | City League results | `/category/cityleague/` |
| 環境デッキ一覧 | Meta deck index | `/category/archetype/` |
| ポケカ飯注目デッキ | Featured decks | `/category/ポケカ飯注目デッキ/` |
| カバンの中身 | Bag/accessory content | `/category/カバンの中身/` |
| ポケカ飯ログ | Site log | `/category/pmeshilog/` |
| Profile | Author profile | `/category/profile/` |

### 2.3 Energy-type tag pages (deck search by type)
Every page has a "各タイプごとのデッキ検索" table linking to tag pages:
- `/tag/grass/` (草), `/tag/fire/` (炎), `/tag/water/` (水), `/tag/lightning/` (雷), `/tag/psychic/` (超), `/tag/fighting/` (闘), `/tag/darkness/` (悪), `/tag/metal/` (鋼), `/tag/dragon/` (ドラゴン), `/tag/colorless/` (無色)

### 2.4 Article URL naming patterns (critical for auto-discovery)
The sitemap reveals **predictable URL patterns** that let us auto-discover content:
- **Tournament result pages:** `/pokemontaikaiwinYYYYMMDD/` (daily winning decks), `/cityleagueYYYYMMDD/`, `/clYYYY<city>/`, `/taikairesult-<env>-<N>w/` (data lab weekly reports)
- **Archetype pages:** `/dorapultex/`, `/bursyamoex/`, `/garurabox/`, `/megarayquazaex/`, `/tetsunoibaraex/`, etc. (deck-name-based slugs)
- **Card list pages:** `/cardlist<set>/` (e.g. `/cardlistm6/`, `/cardlistsv10/`), `/extra-<set>/`
- **Data lab reports:** `/taikairesult-*`, `/datalab-*`

---

## 3. ⭐ The Data Lab documents (ポケカデータラボ) — MOST VALUABLE

The site author is a **ポケカデータラボ (Pokeca Data Lab)** member. This is the "data lab" content the user wants fully imported. There are two key types:

### 3.1 The methodology doc — `/datalab-voluntarycompetition/`
Title: **"ポケカオフシーズン！自主大会データの重要性とご協力依頼"** (Off-season! The importance of independent-tournament data & cooperation request). It explains the **entire data methodology**:

**How they collect data:**
- During the season: City League top-16 deck recipes are public → they compute **share rate (シェア率)** and **points** → build the Tier table.
- Off-season: no official tournaments, so they aggregate **independent tournaments (自主大会)** with **32+ players** for reliability.
- Data is submitted via a **Google Form** (`https://forms.gle/6R99sBshbPgvpHg3A`) by tournament organizers, then cross-checked against X/Twitter posts.

**The point system (ポイントテーブル):**
- Aggregation targets **top 4** (and top 8 for large tournaments).
- Points are awarded by **tournament size × placement**, modeled on City League CSP (Championship Points).
- Team tournaments use the same point table.

**The outputs (アウトプット):**
1. **データレポート (Data Report)** — a "入賞デッキ分布図" (placing-deck distribution chart) + "各デッキポイントランキング" (per-deck point ranking). Image: `自主大会レポート20240611-2.jpg`
2. **Tier表 (Tier table)** — the standard tier ranking. Image: `Tier表_20240613.jpg`

**Validation:** They validated the method by comparing the 3-week off-season aggregation against the official environment announcement — **"大きなブレがなく、トレンドもしっかり抑えれていた"** (no major deviation; trends were well captured). This is a strong signal the data is reliable.

### 3.2 The weekly data lab reports — `/taikairesult-<env>-<N>w/`
These are the **actual aggregated data documents**. Example: `/taikairesult-m6-3w/` = "【自主大会結果まとめ】ストームエメラルダ環境3週目" (Storm Emerald environment, week 3).

**Structure per report:**
- **Header:** environment name + week number, date, link to previous week.
- **Tournament account list** link (`/tournament-list/`).
- **Per-tournament entries**, each with:
  - **Tournament name + size**, e.g. `福福バトルフェスvol.7 ~蒼空を支配する翠玉龍~(58名)`
  - **Date + region + format**, e.g. `開催日：2026/08/11 東京 個人戦` (or 3名チーム for team)
  - **Embedded X/Twitter post** (the source tweet with player handles + date)
  - **Structured placing list**, e.g.:
    ```
    優勝：フーディン
    準優勝：ルカリオ
    ベスト4：レックウザ
    ベスト4：ガブリアス
    ベスト8：ドラパルト
    ベスト8：ドラパルト
    ```
  - **デッキ分布 (deck distribution)** — some tournaments post the full deck-usage distribution image.

**Value:** This is **structured, point-weighted meta data** — exactly comparable to our own deck win rates. The `優勝/準優勝/ベスト4/ベスト8` labels map directly to placements, and tournament size gives us the weight.

---

## 4. Other data we can pull (and its value)

### 4.1 ⭐ Tier list — `/strongestdeck-tire/`
The flagship page: **"【Tier表】ポケカ環境デッキレシピランキング"** (Tier table / meta deck ranking), updated ~weekly (e.g. "2026/8/10 更新").

Per tier (Tier1 → Tier4), each deck entry contains:
- **Deck name** (JP), e.g. バシャーモex＋ドラパルトex, ドラパルトex, ガルーラボックス
- **Reference deck recipe** — a specific tournament placement, e.g. `03/29(日) CL大阪（マスター）：5 位`
- **Deck code** (e.g. `pyUUyU-MV0ErE-MpXUyR`) → resolves to full card list on the official site
- **Deck image** (JP card list screenshot)
- **Link to the deck's dedicated archetype page** (e.g. `/dorapultex/`)
- **Link to the tournament result page** (e.g. `/cl2026osaka/`)

**Value:** A **curated, human-ranked tier list** — the single best "top decks" comparison source.

### 4.2 ⭐ Tournament result pages — `/pokemontaikaiwinYYYYMMDD/`, `/cityleagueYYYYMMDD/`, `/clYYYY.../`
Each page aggregates winning/placing decks from one or more events. Structure per deck:
- **Deck name** (JP)
- **Tournament name + size + placement**, e.g. `カミツオロチデッキ koloyacupチーム戦(198名)：優勝`
- **Deck code** → full card list
- **Deck image**
- **Embedded tweet** (X/Twitter) with the player's post + handle + date
- **Page guide** at top: `📄 P.1` / `📄 P.2` listing deck names + counts per page (e.g. `ドラパルト(4)・タケルライコ(4)・レックウザ(5)`)

**Value:** **Tournament detection + meta share data.** The `(4)`, `(5)` counts are **deck usage counts** — we can compute **meta share %** per deck per event.

### 4.3 ⭐ Archetype pages — `/category/archetype/` + per-deck pages
- **Archetype index** lists all meta decks with dates.
- **Per-deck pages** aggregate every winning/placing recipe for that archetype, each with deck code, image, tournament, placement, and a **deck template** (pre-filled card search).

**Value:** Per-archetype **recipe history** — how a deck evolved and its win record across events.

### 4.4 Deck code → full card list (official Pokemon site)
Every deck code resolves at:
```
https://www.pokemon-card.com/deck/confirm.html/deckID/<CODE>/
```
This returns the **full 60-card list** (card name JP + quantity), e.g. ドラメシヤ ×4, ドロンチ ×4, ドラパルトex ×2, バシャーモex ×2 …
Also available:
- **Image view:** `https://www.pokemon-card.com/deck/thumbs.html/deckID/<CODE>/` (single deck image)
- **Print sheet:** `https://www.pokemon-card.com/deck/print.html/deckID/<CODE>/`

**Value:** **Ground truth for deck composition** — compare a JP deck's card list against our own tracked decks, and auto-detect "what deck is this" from card lists.

### 4.5 Card list reviews — `/category/pokekainfo/pokemoncardlist/`
New-card reviews with **S/A/B/C ranks** per card (e.g. `/cardlistm6/`, `/cardlistsv10/`).

**Value:** Card-tier data for "which cards matter" analysis.

### 4.6 DeckWriter tool — `/deckwriter/`
A tool that takes a deck code and generates a formatted article. Confirms the deck-code → data pipeline is a first-class feature of the site.

### 4.7 Tournament account list — `/tournament-list/`
A curated list of regional independent-tournament X accounts (also on Notion). Useful for discovering more sources.

---

## 5. How to pull data efficiently & future-proof

### 5.1 Recommended architecture: a `japan_data.py` module + "Japan Data" tab

Create a single module `japan_data.py` that owns ALL pokekameshi + deck-code fetching, and a "Japan Data" tab in `StatsUI.py` that renders it. This keeps everything under one umbrella and mirrors the existing `deck_analytics.py` / `_load_meta_cache` patterns.

```
japan_data.py
├── SOURCES (config: URLs, selectors, cache TTLs)
├── discover_articles()          # crawl sitemap + category feeds → new URLs
├── fetch_tier_list()            # /strongestdeck-tire/ → [{tier, deck_jp, deck_en, code, event, placement, url}]
├── fetch_tournament_page(url)   # → {event, date, decks:[{deck_jp, count, code, image, tweet}]}
├── fetch_datalab_report(url)    # /taikairesult-* → {env, week, tournaments:[{name,size,date,region,format,placings}]}
├── fetch_archetype_page(url)    # → {deck_jp, recipes:[{event, placement, code, image}]}
├── resolve_deck_code(code)      # → {cards:[{name_jp, qty}], image_url}
├── translate(deck_jp)           # → English via JP_DECK_TRANSLATION + fallback
├── compute_meta_share(decks)    # → {deck_en: share%}
├── compute_datalab_points(placings, size)  # → per-deck points (CSP-style)
└── cache / refresh logic
```

### 5.2 Future-proofing (don't break on new pages)

1. **Selector-based, not URL-hardcoded.** The site is WordPress; article HTML is consistent. Use stable CSS selectors (e.g. `h3` for deck names, the deck-code block, the `pokemon-card.com/deck/confirm.html/deckID/` link) rather than matching exact page URLs. New tournament pages follow the same template, so they parse automatically.

2. **Discover pages via the sitemap + category feeds.** Instead of hardcoding every article URL, crawl:
   - `sitemap.xml` → `post-sitemap*.xml` (all article URLs + last-modified dates)
   - Category pages (`/category/cityleague/`, `/category/archetype/`, `/category/pokemoncard-windeckrecipe/`) with pagination
   - **URL patterns** (`pokemontaikaiwin*`, `cityleague*`, `taikairesult-*`, `cl*`) to classify new posts automatically
   - This means **new pages are picked up automatically** without code changes.

3. **Cache aggressively with TTLs.** Store fetched data in `.meta_cache_japan.json` (mirroring existing `.meta_cache_*.json`). Refresh the tier list weekly (it updates ~weekly), tournament pages on-demand, and deck-code card lists once (they rarely change). This avoids hammering the site and keeps the app fast.

4. **Graceful degradation.** If a fetch fails (site down, page moved, selector changed), fall back to cached data + show the "Open in Browser" link. Never crash the UI.

5. **Translation layer.** Keep a `JP_DECK_TRANSLATION` map (already exists in `StatsUI.py` for City League S4) and extend it. For unknown deck names, fall back to a **romaji/English guess** or show the JP name with a "translate" affordance. This keeps data relevant to English audiences.

6. **Images & embeds.** Deck images are hosted at `pokekameshi.com/wp-content/uploads/...`. We can:
   - Cache deck images locally (like the existing sprite cache) for the deck icon picker.
   - Show the deck-code image from `pokemon-card.com/deck/thumbs.html/deckID/<CODE>/` — a **clean, English-friendly visual** of the whole deck.
   - Embed the tweet link (X) as a clickable "source" rather than scraping it.

### 5.3 Comparison with our own data (the core value)
The whole point is **comparison**. Proposed "Japan Data" tab sections:
- **JP Tier List** — show Tier1–4 decks with EN names, meta share, and a **"vs My Win Rate"** column (our `deck_analytics.rank_weighted_winrate()` for the same deck).
- **JP Meta Share** — bar chart of deck usage % from tournament pages, overlaid with our own deck usage.
- **JP Data Lab Reports** — the weekly `taikairesult-*` reports, translated + consolidated into a point-weighted deck ranking, filterable by environment/week.
- **JP Tournament Feed** — recent events with winning decks; flag if we've seen that deck in our own battles.
- **Deck Code Viewer** — paste/click a JP deck code → full card list (EN names where possible) + image.

---

## 6. Concrete data model (SQLite-friendly)

```json
{
  "tier_list": {
    "updated": "2026-08-10",
    "tiers": [
      {"tier": 1, "deck_jp": "バシャーモex＋ドラパルトex", "deck_en": "Blaziken ex / Dragapult ex",
       "code": "pyUUyU-MV0ErE-MpXUyR", "event": "CL Osaka", "placement": "5th", "url": "/bursyamoex/"}
    ]
  },
  "datalab_reports": [
    {"slug": "taikairesult-m6-3w", "env": "Storm Emerald", "week": 3, "date": "2026-08-17",
     "tournaments": [
       {"name": "福福バトルフェスvol.7", "size": 58, "date": "2026-08-11", "region": "Tokyo",
        "format": "individual", "tweet_url": "...",
        "placings": [{"place": "1st", "deck_jp": "フーディン", "deck_en": "Alakazam"},
                     {"place": "2nd", "deck_jp": "ルカリオ", "deck_en": "Lucario"},
                     {"place": "top4", "deck_jp": "レックウザ", "deck_en": "Rayquaza"}]}
     ]}
  ],
  "tournaments": [
    {"slug": "pokemontaikaiwin20260816", "date": "2026-08-16", "title_jp": "...",
     "decks": [{"deck_jp": "カミツオロチ", "deck_en": "Iron Thorns ex", "count": 2,
                "code": "xc4cxx-dXle6X-aGGDx8", "image": "...", "tweet_url": "..."}]}
  ],
  "archetypes": [
    {"deck_jp": "ドラパルトex", "deck_en": "Dragapult ex", "url": "/dorapultex/",
     "recipes": [{"event": "...", "placement": "1st", "code": "4GGxYc-KmW2Iv-8c4c8c"}]}
  ],
  "deck_codes": {
    "pyUUyU-MV0ErE-MpXUyR": {"cards": [{"name_jp": "ドラメシヤ", "qty": 4}, ...], "image": "..."}
  }
}
```

---

## 7. Recommended implementation order

1. **`japan_data.py`** — fetch tier list + tournament pages + **data lab reports** + resolve deck codes, with cache & translation. (Core, highest value.)
2. **"Japan Data" tab** in `StatsUI.py` — replace/expand the current "Japan CL" tab into a multi-section Japan Data tab (Tier List, Meta Share, Data Lab Reports, Tournament Feed, Deck Code Viewer).
3. **Comparison columns** — wire JP meta share / tier / data-lab points into `deck_analytics` so we can show "JP meta share vs my win rate".
4. **Deck image caching** — reuse the sprite-cache pattern for deck images.
5. **Auto-discovery** — crawl sitemap/category feeds so new pages are picked up without code changes.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Site is Japanese-only | Translation map + romaji fallback; keep EN names primary |
| HTML/selector changes | Selector-based parsing + graceful fallback to cached data + browser link |
| Rate limiting / blocking (429 seen) | Cache with TTLs, throttle requests, respect robots.txt |
| Deck codes expire | Cache card lists; if a code 404s, show image/link instead |
| Copyright / ToS | Link to source, cache images locally for personal use, don't redistribute |
| New page types | Auto-discovery via sitemap/category feeds; generic parser |
| Data lab reports vary in format | Parse the structured `優勝/準優勝/ベスト4/ベスト8` lines; fall back to tweet text |

---

## 9. Key URLs reference

| Purpose | URL |
|---|---|
| Tier list | `https://pokekameshi.com/strongestdeck-tire/` |
| Data lab methodology | `https://pokekameshi.com/datalab-voluntarycompetition/` |
| Data lab weekly reports | `https://pokekameshi.com/taikairesult-*/` (e.g. `taikairesult-m6-3w`) |
| Deck list (archetype) | `https://pokekameshi.com/category/archetype/` |
| City League results | `https://pokekameshi.com/category/cityleague/` |
| Winning deck roundups | `https://pokekameshi.com/category/pokemoncard-windeckrecipe/` |
| Card list reviews | `https://pokekameshi.com/category/pokekainfo/pokemoncardlist/` |
| Tournament account list | `https://pokekameshi.com/tournament-list/` |
| Sitemap index | `https://pokekameshi.com/sitemap.xml` |
| Post sitemaps | `https://pokekameshi.com/post-sitemap.xml` … `post-sitemap4.xml` |
| Category sitemap | `https://pokekameshi.com/category-sitemap.xml` |
| DeckWriter tool | `https://pokekameshi.com/deckwriter/` |
| Deck code → card list | `https://www.pokemon-card.com/deck/confirm.html/deckID/<CODE>/` |
| Deck code → image | `https://www.pokemon-card.com/deck/thumbs.html/deckID/<CODE>/` |
| Deck code → print | `https://www.pokemon-card.com/deck/print.html/deckID/<CODE>/` |
