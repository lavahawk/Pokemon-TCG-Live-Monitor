"""
TrainerHill Meta Trend (tools.trainerhill.com/dashboards/meta-trend) as a data
source for the Meta tab's Trend view. TrainerHill does the counting; we only
call the same backend its page uses and draw the result ourselves.

Backend (a "BFF" for the Next.js page):
  GET  /api/v1/bff/session                         -> anonymous session cookie + csrf_token
  POST /api/v1/bff/queries/deck_archetype_breakdown -> every archetype: id, name, icons, count, share
  POST /api/v1/bff/queries/meta_trend               -> per day: players per chosen archetype

Both queries take the page's filters: game, format, start_date, tie_value,
min_players, sources ("play" = online events, "labs" = in-person events).
"""

import time

BASE = "https://tools.trainerhill.com"
API = f"{BASE}/api/v1/bff"
PAGE_URL = f"{BASE}/dashboards/meta-trend/"
TIMEOUT = (8, 30)
CACHE_TTL_S = 15 * 60

SOURCES = {"play": "Online", "labs": "In-person"}

_state = {"session": None, "csrf": None, "at": 0.0}
_cache = {}


def _session():
    """A requests session holding TrainerHill's anonymous BFF cookie (renewed
    every few hours, or after a 401)."""
    import requests
    if _state["session"] is None or time.time() - _state["at"] > 3 * 3600:
        session = requests.Session()
        from version import VERSION
        session.headers.update({"User-Agent": f"TCGLiveMonitor/{VERSION}", "Origin": BASE, "Referer": PAGE_URL})
        response = session.get(f"{API}/session", timeout=TIMEOUT)
        response.raise_for_status()
        _state.update(session=session, csrf=(response.json() or {}).get("csrf_token"), at=time.time())
    return _state["session"]


def _post(query, body):
    key = (query, tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in body.items())))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_S:
        return hit[1]
    for attempt in range(3):
        session = _session()
        headers = {"X-CSRF-Token": _state["csrf"]} if _state["csrf"] else {}
        response = session.post(f"{API}/queries/{query}", json=body, headers=headers, timeout=TIMEOUT)
        if response.status_code == 401 and attempt < 2:
            _state["session"] = None  # session expired: start a new one
            continue
        if response.status_code >= 500 and attempt < 2:
            time.sleep(1.5)  # their gateway times out now and then; the retry usually works
            continue
        response.raise_for_status()
        result = (response.json() or {}).get("result") or {}
        _cache[key] = (time.time(), result)
        return result
    raise RuntimeError("TrainerHill session was refused")


def filters(start_date, sources=("play", "labs"), min_players=32, tie_value=1.0 / 3.0):
    return {"game": "ptcg", "format": "STANDARD", "start_date": start_date,
            "tie_value": f"{tie_value:.10f}", "min_players": int(min_players), "sources": list(sources)}


def breakdown(params):
    """{"total_events", "total_players", "archetypes": [{id, name, icons, count, percentage, avg_placing}]}"""
    return _post("deck_archetype_breakdown", params)


def trend(params, deck_ids):
    """{"total_events", "total_players", "daily_trend": [{date, total_players, decks: [{deck_id, count, ...}]}]}"""
    if not deck_ids:
        return {"total_events": 0, "total_players": 0, "daily_trend": []}
    return _post("meta_trend", dict(params, deck_ids=list(deck_ids)))


def series(result, deck_ids, smooth_days=1):
    """(dates, {deck_id: (counts, shares)}) with every day present for every
    deck. Share = that deck's players / the chosen decks' players that day,
    like TrainerHill's own chart. smooth_days > 1 = trailing window sums."""
    days = result.get("daily_trend") or []
    dates = [d["date"] for d in days]
    counts = {deck: [0] * len(days) for deck in deck_ids}
    totals = [0] * len(days)
    for i, day in enumerate(days):
        for d in day.get("decks") or []:
            if d.get("deck_id") in counts:
                counts[d["deck_id"]][i] = int(d.get("count") or 0)
        totals[i] = sum(counts[deck][i] for deck in deck_ids)
    if smooth_days > 1:
        def window(values):
            return [sum(values[max(0, i - smooth_days + 1):i + 1]) for i in range(len(values))]
        counts = {k: window(v) for k, v in counts.items()}
        totals = window(totals)
    out = {}
    for deck, values in counts.items():
        shares = [100.0 * v / t if t else 0.0 for v, t in zip(values, totals)]
        out[deck] = (values, shares)
    return dates, out


def summary(result, deck_ids, recent_days=7):
    """Per deck: players, share of the period, share in the last `recent_days`
    and the change vs the `recent_days` before (percentage points)."""
    days = result.get("daily_trend") or []
    n = len(days)

    def share(lo, hi):
        tally, total = {}, 0
        for day in days[max(0, lo):max(0, hi)]:
            for d in day.get("decks") or []:
                if d.get("deck_id") in deck_ids:
                    tally[d["deck_id"]] = tally.get(d["deck_id"], 0) + int(d.get("count") or 0)
                    total += int(d.get("count") or 0)
        return {k: 100.0 * tally.get(k, 0) / total if total else 0.0 for k in deck_ids}, tally
    whole, players = share(0, n)
    latest, _ = share(n - recent_days, n)
    before, _ = share(n - 2 * recent_days, n - recent_days)
    return {k: {"players": players.get(k, 0), "share": whole[k], "latest": latest[k],
                "trend": latest[k] - before[k]} for k in deck_ids}
