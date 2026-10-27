"""
Meta -> Trend from our own event cache: the meta sheet's "trend_events"
(players per archetype in every online and in-person event of the window,
see meta_sources._assemble). Instant and offline - nothing is downloaded.

breakdown() and trend() return the same shapes as trainerhill_trend's
(TrainerHill counts the same Limitless events), so trainerhill_trend.series
and .summary draw both.
"""

SOURCES = {"online": "Online", "in_person": "In-person"}
_OLD_KEYS = {"play": "online", "labs": "in_person"}  # TrainerHill's names, in old settings


def source_keys(keys):
    """Saved source keys in this module's names (older settings used TrainerHill's)."""
    out = []
    for k in keys or ():
        k = _OLD_KEYS.get(k, k)
        if k in SOURCES and k not in out:
            out.append(k)
    return out


def _events(sheet, start, sources, min_players):
    sources = set(source_keys(sources))
    return [e for e in (sheet or {}).get("trend_events") or []
            if e["d"] >= start and e["k"] in sources and int(e.get("p") or 0) >= int(min_players or 0)]


def breakdown(sheet, start, sources, min_players=0):
    """{"total_events", "total_players", "archetypes": [{id, name, icons, count, percentage}]}
    (percentage is a fraction of all players, biggest deck first)."""
    events = _events(sheet, start, sources, min_players)
    names = (sheet or {}).get("trend_names") or {}
    counts = {}
    for e in events:
        for deck, n in e["c"].items():
            counts[deck] = counts.get(deck, 0) + n
    total = sum(counts.values())
    archetypes = []
    for deck, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        name, icons = (names.get(deck) or [deck, []])[:2]
        archetypes.append({"id": deck, "name": name, "icons": icons, "count": n,
                           "percentage": n / total if total else 0.0})
    return {"total_events": len(events), "total_players": total, "archetypes": archetypes}


def trend(sheet, start, sources, deck_ids, min_players=0):
    """{"total_events", "total_players", "daily_trend": [{date, total_players, decks: [{deck_id, count}]}]}
    for the chosen decks; only days with events are listed."""
    chosen = set(deck_ids or ())
    events = _events(sheet, start, sources, min_players)
    days = {}
    for e in events:
        day = days.setdefault(e["d"], {})
        for deck, n in e["c"].items():
            if deck in chosen:
                day[deck] = day.get(deck, 0) + n
    daily = [{"date": d, "total_players": sum(decks.values()),
              "decks": [{"deck_id": k, "count": v} for k, v in decks.items()]}
             for d, decks in sorted(days.items())]
    return {"total_events": len(events), "total_players": sum(x["total_players"] for x in daily),
            "daily_trend": daily}


def movers(summary, names, threshold=1.0):
    """(rising, falling): the chosen decks whose share of the last 7 days moved
    by more than `threshold` points, biggest move first, as (name, change)."""
    moves = [(names.get(deck, deck), s["trend"]) for deck, s in summary.items()]
    rising = sorted((m for m in moves if m[1] > threshold), key=lambda m: -m[1])
    falling = sorted((m for m in moves if m[1] < -threshold), key=lambda m: m[1])
    return rising, falling
