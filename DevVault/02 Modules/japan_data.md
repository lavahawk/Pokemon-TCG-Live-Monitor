---
tags: [module, integration, removed]
file: japan_data.py (removed 2026-10-13)
---
# japan_data.py: removed

The pokekameshi.com scraper (tier list, hard-coded winner / data-lab pages, OpenAI name translation) was **removed on 2026-10-13**. Its City League numbers came from the same official top-16 lists that Limitless JP already carries, so they couldn't be added to the meta sheet without double-counting. It was also fragile (BUG-027).

The **Japan Data** tab now reads Limitless City Leagues from the meta sheet's event cache: `meta_sources.japan_view(since, sheet_rows)` gives per-archetype points (16 for 1st … 1 for 16th), top-16 count, share, top 4, wins, average placing and a trend (newer half vs older half of the period). Names follow the Meta tab (same icons = same archetype). See [[Data Sources]] and [[StatsUI]].

Left on disk and unused: `.meta_cache_japan.json`, `.japan_translation_cache.json`.
