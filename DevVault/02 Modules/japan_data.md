---
tags: [module, integration]
file: japan_data.py
lines: 902
---
# japan_data.py: Japanese meta

Scrapes pokekameshi.com: the tier list (`/strongestdeck-tire/`), 5 **hard-coded** daily winner pages (`pokemontaikaiwin2026080x–0816`) and 5 hard-coded data-lab weekly reports (`taikairesult-m6-3w … m5-9w`). It parses HTML with regex (h2/h3 headings, `優勝/準優勝/ベスト4/ベスト8：deck` lines), weights placings, translates names (static map → cache → optional gpt-4o) and outputs Limitless-shaped rows. Cache 1 h (`.meta_cache_japan.json`).

Problems: all under BUG-027 in [[Bug Register]]. Summary: stale sources, rows get 100% win rate (finishes ≠ wins, so hide the WR/Bayes/P>50 columns for Japan or model "share" only), the first-substring translation, duplicate/wrong dictionary entries, 2 AI calls per name, and a timeframe filter that's a placeholder (all options return the same rows).

Fix direction: discover slugs from `sitemap.xml` (constant already defined, unused); use BeautifulSoup (already a dependency); use the longest-match translation; batch the AI translation through `hard_refresh_translations`.
