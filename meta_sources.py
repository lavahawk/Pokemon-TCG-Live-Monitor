"""
Unified meta sheet: one weighted view of the Standard meta built from

  * play.limitlesstcg.com   online tournaments  - shares, W/L records, matchups
  * limitlesstcg.com        in-person events    - shares + placement points
  * labs.limitlesstcg.com   in-person pairings  - W/L records, matchups (every
                            round, every player: labs knows the whole field's decks)
  * limitlesstcg.com/jp     Japanese City Leagues (Bo1) - shares + placements

Every event gets a weight:

    source  : online 1.0 | in-person 1.75 | World Championship 3.0
              Japan x0.75 (best-of-one)
              (in-person / Worlds boosts only apply to the CURRENT format -
               after a new expansion they count like any other event)
    era     : events since the latest expansion 1.0, one expansion back 0.7,
              two back 0.4, older events are dropped
    size    : sqrt(players / 64), clipped to 0.5-3 (big events say more)

Expansion release dates come from the Limitless card database (EN and JP
calendars; JP events are dated against JP releases). Small products
(starter decks, premium sets) don't count as expansions.

Per-event results are cached forever in .meta_store/ (finished events never
change), so a refresh only downloads new events. The output is written to
.meta_cache_limitless_standard.json in the same row format the dashboard
already uses (deck, icons, share, wins, losses, ties, win_pct, ...), plus:
    sources   {online, in_person, japan}  number of events seen in
    top_share weighted share among in-person / JP top finishers (%)
    matchups  {opponent_key: [w, l, t]}   weighted, from online pairings
"""

import html
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from deck_analytics import normalize_deck_name, win_rate_posterior

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(BASE_DIR, ".meta_store")
SHEET_FILE = os.path.join(BASE_DIR, ".meta_cache_limitless_standard.json")
SCHEMA_VERSION = 3

LIMITLESS = "https://limitlesstcg.com"
LABS = "https://labs.limitlesstcg.com"
PLAY_API = "https://play.limitlesstcg.com/api"

def current_weights():
    """Meta weights from Advanced → Preferences (weights.py), as used below."""
    from weights import load_weights, era_weights
    meta = load_weights()["meta"]
    return {"online": meta["online"], "in_person": meta["in_person"], "worlds": meta["worlds"],
            "japan": meta["japan"], "era": era_weights()}


WEIGHTS = current_weights()  # refreshed at the start of every build
MIN_EXPANSION_CARDS = 90        # smaller products (starters, premium decks) aren't expansions
ONLINE_MIN_PLAYERS = 32
ONLINE_MAX_EVENTS = 80
JP_MAX_EVENTS = 150
EXPANSION_TTL = 24 * 3600
REQUEST_WORKERS = 4
TIMEOUT = (8, 20)        # (connect, read) seconds


# ── HTTP ───────────────────────────────────────────────────────────────────
def make_session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    from version import VERSION
    session.headers["User-Agent"] = f"TCGLiveMonitor/{VERSION} (+https://github.com/lavahawk/Pokemon-TCG-Live-Monitor)"
    # Short, bounded retries: a slow endpoint must never stall the whole build.
    retry = Retry(total=2, connect=2, read=1, backoff_factor=0.5,
                  status_forcelist=(429, 500, 502, 503, 504), respect_retry_after_header=False)
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=REQUEST_WORKERS * 2))
    return session


def _soup(session, url):
    from bs4 import BeautifulSoup
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def _store_path(name):
    os.makedirs(STORE_DIR, exist_ok=True)
    return os.path.join(STORE_DIR, re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".json")


def _cached(name, builder, ttl=None):
    """Load a cached JSON blob, or build + save it. ttl None = keep forever."""
    path = _store_path(name)
    if os.path.exists(path) and (ttl is None or time.time() - os.path.getmtime(path) < ttl):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            pass
    data = builder()
    if data is not None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(tmp, path)
    return data


def _parse_short_date(text):
    """'16 Sep 26' -> '2026-09-16'."""
    try:
        return datetime.strptime(text.strip(), "%d %b %y").date().isoformat()
    except ValueError:
        return None


# ── Expansions ─────────────────────────────────────────────────────────────
def fetch_expansions(session, region="en"):
    """[{code, name, date, cards}] newest first; only real expansions."""
    def build():
        soup = _soup(session, f"{LIMITLESS}/cards" + ("/jp" if region == "jp" else ""))
        sets = []
        for tr in soup.select("table tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if len(cells) < 3:
                continue
            name_code, released, cards = cells[0], cells[1], cells[2]
            iso = _parse_short_date(released)
            count = re.match(r"(\d+)", cards)
            if not iso or not count:
                continue
            parts = name_code.rsplit(" ", 1)
            sets.append({"name": parts[0], "code": parts[1] if len(parts) > 1 else "",
                         "date": iso, "cards": int(count.group(1))})
        return sets
    sets = _cached(f"expansions_{region}", build, ttl=EXPANSION_TTL) or []
    today = date.today().isoformat()
    sets = [s for s in sets if s["cards"] >= MIN_EXPANSION_CARDS and s["date"] <= today]
    sets.sort(key=lambda s: s["date"], reverse=True)
    return sets


def era_of(event_date, expansions, legal=None):
    """How many expansions newer than the event's format (0 = current).

    Uses the event's legal set range when known ("Temporal Forces – Pitch
    Black" -> newest legal set Pitch Black): new sets become tournament-legal
    a little after release, so an event a few days after a release is still
    the previous format. Falls back to the release dates.
    """
    if legal:
        newest = legal.split("–")[-1].split(" - ")[-1].strip().lower()
        for index, s in enumerate(expansions):
            if s["name"].lower() == newest:
                return index
    return sum(1 for s in expansions if s["date"] > event_date)


# ── In-person (limitlesstcg.com) ───────────────────────────────────────────
def list_in_person(session):
    soup = _soup(session, f"{LIMITLESS}/tournaments?time=12months&format=standard")
    events = []
    for tr in soup.select("table.completed-tournaments tr[data-date]"):
        link = tr.select_one("a[href^='/tournaments/']")
        if not link:
            continue
        tid = link["href"].rsplit("/", 1)[-1]
        events.append({"id": tid, "date": tr["data-date"], "name": tr.get("data-name", ""),
                       "players": int(tr.get("data-players") or 0)})
    return events


def fetch_in_person_event(session, event):
    def build():
        soup = _soup(session, f"{LIMITLESS}/tournaments/{event['id']}/statistics")
        decks = []
        for tr in soup.select("table tr[data-count]"):
            link = tr.select_one("a[href^='/decks/']")
            if not link:
                continue
            icons = [img.get("alt") for img in tr.select("img.pokemon") if img.get("alt")]
            name = link.get_text(" ", strip=True)
            count = int(tr["data-count"])
            points = int(tr.get("data-points") or 0)
            # The row groups variants ("Dragapult" = all Dragapult builds); its
            # tooltip has the split ("44 Dragapult\n6 Dragapult Dusknoir").
            # Split count and points by variant so they line up with online data.
            tip = tr.select_one("[data-tooltip]")
            variants = []
            for line in (tip.get("data-tooltip", "") if tip else "").splitlines():
                m = re.match(r"\s*(\d+)\s+(.+?)\s*$", line)
                if m:
                    variants.append((int(m.group(1)), m.group(2)))
            if len(variants) > 1 and sum(c for c, _ in variants) == count:
                for v_count, v_name in variants:
                    decks.append({"deck": v_name, "deck_id": link["href"].rsplit("/", 1)[-1] if v_name == name else None,
                                  "icons": icons if v_name == name else [], "count": v_count,
                                  "points": round(points * v_count / count, 2)})
            else:
                decks.append({"deck": name, "deck_id": link["href"].rsplit("/", 1)[-1],
                              "icons": icons, "count": count, "points": points})
        return {"event": event, "decks": decks}
    return _cached(f"inperson_v2_{event['id']}", build)


def _labs_get(session, url):
    # Labs doesn't declare a charset, so requests would decode it as Latin-1.
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.content.decode("utf-8", "replace")


def list_labs(session):
    """Limitless Labs events: [{labs_id, name, date}] (index page, cached 6 h)."""
    def build():
        page = _labs_get(session, f"{LABS}/")
        events, seen = [], set()
        for lid, body in re.findall(r'href="/(\d{4})/[a-z]*"[^>]*>(.*?)</a>', page, re.S):
            text = html.unescape(" ".join(re.sub(r"<[^>]+>", " ", body).split()))
            m = re.search(r"([A-Z][a-z]+) (\d{1,2})(?!\d).*?(\d{4})", text)
            if lid in seen or not m:
                continue
            try:
                start = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
            except ValueError:
                continue
            seen.add(lid)
            events.append({"labs_id": lid, "name": text[:m.start()].strip(), "date": start.isoformat()})
        return events
    return _cached("labs_index", build, ttl=6 * 3600)


def match_labs_event(event, labs_events):
    """The Labs event behind a limitlesstcg.com in-person event: start within
    3 days and a shared place word ("Lousville" ~ "Louisville")."""
    from difflib import SequenceMatcher
    try:
        day = date.fromisoformat(event["date"][:10])
    except (KeyError, ValueError):
        return None

    def words(text):
        return [w for w in re.findall(r"[a-z]+", (text or "").casefold())
                if len(w) >= 4 and w not in ("regional", "championship", "championships", "special", "event",
                                             "international", "cup", "league")]
    mine = words(event.get("name"))
    best, best_score = None, 0.0
    for lab in labs_events:
        try:
            gap = abs((date.fromisoformat(lab["date"]) - day).days)
        except ValueError:
            continue
        if gap > 3:
            continue
        score = max((SequenceMatcher(None, a, b).ratio() for a in mine for b in words(lab["name"])), default=0.0)
        if score > best_score:
            best, best_score = lab, score
    return best if best_score >= 0.8 else None


def _labs_icons(fragment):
    return tuple(sorted(re.search(r'alt="([^"]+)"', tag).group(1)
                        for tag in re.findall(r'<img[^>]*class="pokemon"[^>]*>', fragment)
                        if re.search(r'alt="([^"]+)"', tag)))


def fetch_labs_results(session, event, labs_id):
    """Every round's pairings of a Labs event, aggregated per archetype slug:
    records, matchups and each player's record (for the pilot design effect).
    Labs shows nearly every player's deck, Day 1 included, so this is the full
    field, not only the players who made Day 2."""
    def build():
        decks_page = _labs_get(session, f"{LABS}/{labs_id}/decks")
        decks = {}
        for row in re.findall(r"<tr>(.*?)</tr>", decks_page, re.S):
            m = re.search(rf'href="/{labs_id}/decks/([a-z0-9\-]+)">([^<]+)</a>', row)
            if m:
                decks[m.group(1)] = {"name": html.unescape(m.group(2)).strip(), "icons": list(_labs_icons(row))}
        by_icons = {}
        for slug, d in decks.items():
            by_icons.setdefault(tuple(sorted(d["icons"])), []).append(slug)
        # Archetypes sharing the same icons (Basic Box / Clefairy Ogerpon):
        # their own pages list their players.
        known_players = {}
        for slugs in by_icons.values():
            if len(slugs) > 1:
                for slug in slugs:
                    page = _labs_get(session, f"{LABS}/{labs_id}/decks/{slug}")
                    for pid in re.findall(rf'href="/{labs_id}/player/(\d+)"', page):
                        known_players.setdefault(pid, slug)

        first = _labs_get(session, f"{LABS}/{labs_id}/pairings?round=1")
        rounds = max([int(x) for x in re.findall(r"\?round=(\d+)", first)] or [0])
        player_deck, pilots = {}, {}
        records, matchups = {}, {}
        games = unknown = 0
        cell = re.compile(r'<td class="w-\[45%\][^"]*?svelte-[a-z0-9]+\s*([a-z ]*)">(.*?)</td>', re.S)
        for rnd in range(1, rounds + 1):
            page = first if rnd == 1 else _labs_get(session, f"{LABS}/{labs_id}/pairings?round={rnd}")
            for row in re.findall(r"<tr>(.*?)</tr>", page, re.S):
                cells = cell.findall(row)
                if len(cells) != 2:
                    continue
                sides = []
                for cls, body in cells:
                    pid = re.search(rf'href="/{labs_id}/player/(\d+)"', body)
                    if not pid:
                        break
                    pid = pid.group(1)
                    if pid not in player_deck:
                        slugs = by_icons.get(_labs_icons(body)) or []
                        player_deck[pid] = slugs[0] if len(slugs) == 1 else known_players.get(pid)
                    sides.append((pid, cls))
                if len(sides) != 2:
                    continue  # bye
                (p1, c1), (p2, c2) = sides
                r1 = 0 if "winner" in c1 else 2 if "tie" in c1 else 1 if "winner" in c2 else None
                if r1 is None:
                    continue  # unreported / double loss
                d1, d2 = player_deck.get(p1), player_deck.get(p2)
                if not (d1 and d2):
                    unknown += 1
                    continue
                games += 1
                for me, opp, slot, pid in ((d1, d2, r1, p1), (d2, d1, (1, 0, 2)[r1], p2)):
                    records.setdefault(me, [0, 0, 0])[slot] += 1
                    matchups.setdefault(me, {}).setdefault(opp, [0, 0, 0])[slot] += 1
                    pr = pilots.setdefault(pid, [me, 0.0, 0])
                    pr[1] += (1.0, 0.0, 0.5)[slot]
                    pr[2] += 1
        by_deck = {}
        for deck, x, n in pilots.values():
            by_deck.setdefault(deck, []).append([x, n])
        return {"event": event, "labs_id": labs_id, "rounds": rounds, "games": games, "unknown": unknown,
                "decks": decks, "records": records, "matchups": matchups, "pilots": by_deck}
    return _cached(f"labs_{labs_id}", build)


def fetch_in_person_standings(session, event):
    """Every listed (Day 2) placing: [{rank, deck, deck_id}], plus the legal set range."""
    def build():
        soup = _soup(session, f"{LIMITLESS}/tournaments/{event['id']}")
        placings = []
        for tr in soup.select("table tr[data-rank]"):
            link = tr.select_one("a[href^='/decks/']")
            rank = re.match(r"(\d+)", tr.get("data-rank", ""))
            if rank and tr.get("data-deck"):
                placings.append({"rank": int(rank.group(1)), "deck": tr["data-deck"],
                                 "deck_id": link["href"].rsplit("/", 1)[-1] if link else None})
        info = soup.select_one(".infobox")
        legal = None
        if info:
            # e.g. "... Players • | Temporal Forces - 30th Celebration | Pairings | ..."
            for part in info.get_text("|", strip=True).split("|"):
                m = re.fullmatch(r"\s*([A-Z0-9][\w' .:&]+?)\s+-\s+([A-Z0-9][\w' .:&]+?)\s*", part)
                if m:
                    legal = f"{m.group(1)} – {m.group(2)}"
                    break
        return {"event": event, "placings": placings, "legal": legal}
    return _cached(f"inperson_standings_v2_{event['id']}", build)


# ── Japan City Leagues (limitlesstcg.com/tournaments/jp) ───────────────────
def list_japan(session):
    soup = _soup(session, f"{LIMITLESS}/tournaments/jp?time=3months&show=100")
    events = []
    for tr in soup.select("table.completed-tournaments tr[data-date]"):
        link = tr.select_one("a[href*='/tournaments/jp/']")
        if not link:
            continue
        events.append({"id": link["href"].rstrip("/").rsplit("/", 1)[-1], "date": tr["data-date"],
                       "name": f"City League {tr.get('data-city', '')}".strip(), "players": 0})
    return events[:JP_MAX_EVENTS]


def fetch_japan_event(session, event):
    def build():
        soup = _soup(session, f"{LIMITLESS}/tournaments/jp/{event['id']}")
        placings = []
        table = soup.select_one("table")
        for tr in (table.select("tr") if table else []):
            cells = tr.select("td")
            if len(cells) < 3:
                continue
            rank = re.match(r"(\d+)", cells[0].get_text(strip=True))
            icons = [img.get("alt") for img in cells[2].select("img.pokemon") if img.get("alt")]
            if rank and icons:
                placings.append({"rank": int(rank.group(1)), "icons": icons})
        return {"event": event, "placings": placings}
    return _cached(f"japan_{event['id']}", build)


# ── Online (play.limitlesstcg.com API) ─────────────────────────────────────
def list_online(session, since_iso):
    events = []
    for page in range(1, 8):
        response = session.get(f"{PLAY_API}/tournaments",
                               params={"game": "PTCG", "format": "STANDARD", "limit": 50, "page": page}, timeout=TIMEOUT)
        response.raise_for_status()
        batch = response.json() or []
        if not batch:
            break
        for t in batch:
            day = (t.get("date") or "")[:10]
            if day and day >= since_iso and int(t.get("players") or 0) >= ONLINE_MIN_PLAYERS:
                events.append({"id": t["id"], "date": day, "name": t.get("name", ""), "players": int(t.get("players") or 0)})
        if (batch[-1].get("date") or "")[:10] < since_iso or len(events) >= ONLINE_MAX_EVENTS:
            break
    return events[:ONLINE_MAX_EVENTS]


def fetch_online_event(session, event):
    def build():
        standings = session.get(f"{PLAY_API}/tournaments/{event['id']}/standings", timeout=TIMEOUT).json() or []
        players = {}
        decks = []
        for p in standings:
            deck = p.get("deck") or {}
            if isinstance(deck, str):
                deck = {"id": deck, "name": deck}
            name = deck.get("name") or deck.get("id")
            if not name:
                continue
            rec = p.get("record") or {}
            entry = {"deck": name, "deck_id": deck.get("id") or name, "icons": deck.get("icons") or [],
                     "w": int(rec.get("wins", 0) or 0), "l": int(rec.get("losses", 0) or 0),
                     "t": int(rec.get("ties", 0) or 0)}
            decks.append(entry)
            if p.get("player"):
                players[p["player"]] = name
        matchups = {}
        try:
            pairings = session.get(f"{PLAY_API}/tournaments/{event['id']}/pairings", timeout=TIMEOUT).json() or []
        except Exception:
            pairings = []
        for m in pairings:
            a, b, winner = m.get("player1"), m.get("player2"), m.get("winner")
            da, db = players.get(a), players.get(b)
            if not (da and db) or winner in (None, -1):
                continue
            for me, opp, i_won in ((da, db, winner == a), (db, da, winner == b)):
                rec = matchups.setdefault(me, {}).setdefault(opp, [0, 0, 0])
                if winner == 0:
                    rec[2] += 1
                elif i_won:
                    rec[0] += 1
                else:
                    rec[1] += 1
        return {"event": event, "decks": decks, "matchups": matchups}
    return _cached(f"online_{event['id']}", build)


FETCH_BUDGET_S = 150  # per source; unfinished events are retried on the next refresh


def _fetch_labs(session, in_person, progress):
    """{limitless event id: aggregated Labs results} for the events Labs covers."""
    try:
        labs_events = list_labs(session)
    except Exception as exc:
        progress(f"  Limitless Labs index unavailable ({exc}) - in-person records skipped")
        return {}
    pairs = [(ev, match_labs_event(ev, labs_events)) for ev in in_person]
    jobs = [dict(ev, labs_id=lab["labs_id"]) for ev, lab in pairs if lab]
    done = _fetch_all(session, lambda sess, ev: fetch_labs_results(sess, ev, ev["labs_id"]),
                      jobs, "in-person results (Labs)", progress)
    return {d["event"]["id"]: d for d in done}


def _fetch_all(session, fn, events, label, progress):
    """Fetch events in parallel within a time budget (cached ones are instant).
    Events that fail or don't finish in time are skipped for this build."""
    from concurrent.futures import as_completed, TimeoutError as FutureTimeout
    results = []
    if not events:
        return results
    pool = ThreadPoolExecutor(max_workers=REQUEST_WORKERS)
    futures = [pool.submit(fn, session, ev) for ev in events]
    done = 0
    try:
        for future in as_completed(futures, timeout=FETCH_BUDGET_S):
            done += 1
            try:
                data = future.result()
            except Exception:
                data = None
            if data:
                results.append(data)
            if done % 10 == 0 or done == len(events):
                progress(f"  {label}: {done}/{len(events)}")
    except FutureTimeout:
        progress(f"  {label}: time budget reached at {done}/{len(events)} - the rest load next refresh")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results


# ── Build the unified sheet ────────────────────────────────────────────────
def _event_weight(kind, event, era):
    if era >= len(WEIGHTS["era"]):
        return 0.0
    w = WEIGHTS["era"][era]
    if kind == "online":
        w *= WEIGHTS["online"]
    else:
        boost = WEIGHTS["in_person"]
        if "world championship" in (event.get("name") or "").lower():
            boost = WEIGHTS["worlds"]
        # In-person boosts only while the event is in the current format.
        w *= boost if era == 0 else 1.0
        if kind == "japan":
            w *= WEIGHTS["japan"]
    players = event.get("players") or 0
    size = math.sqrt(players / 64.0) if players else 1.0
    return w * max(0.5, min(3.0, size))


def _key(name):
    return normalize_deck_name(re.sub(r"\bex\b", "", name or "", flags=re.IGNORECASE)) or (name or "").lower()


def _pokemon_signature(name):
    """Order-free set of Pokemon in an archetype name, ignoring Mega/ex."""
    return frozenset(t for t in _key(name).split() if t not in ("mega", "ex"))


def _name_from_icons(icons):
    """Sprite names -> readable archetype name: 'lucario-mega' -> 'Mega Lucario'."""
    parts = []
    for icon in icons:
        base = icon.lower()
        mega = base.endswith("-mega")
        base = base[:-5] if mega else base
        word = " ".join(w.capitalize() for w in base.split("-"))
        parts.append(f"Mega {word}" if mega else word)
    return " ".join(parts)


def _in_person_summary(ip, totals):
    """Day 2 / Top 32 / Top 8 / wins counts and weighted conversion.

    conversion = (share of Top 32 spots) / (share of Day 2 spots): 1.0 means
    the deck reaches the top as often as its popularity predicts; 1.5 means
    50% more often. Top-8 rate likewise. None without Day 2 data.
    """
    if not ip["day2"]:
        return None
    day2_share = ip["w_day2"] / totals["day2"] if totals["day2"] else 0.0
    conv32 = (ip["w_top32"] / totals["top32"]) / day2_share if totals["top32"] and day2_share else None
    conv8 = (ip["w_top8"] / totals["top8"]) / day2_share if totals["top8"] and day2_share else None
    return {
        "day2": ip["day2"], "top32": ip["top32"], "top8": ip["top8"], "wins": ip["wins"],
        "day2_share": round(day2_share * 100.0, 2),
        "conversion_top32": round(conv32, 2) if conv32 is not None else None,
        "conversion_top8": round(conv8, 2) if conv8 is not None else None,
        "best": ip["best"],
    }


ALL_SOURCES = ("online", "in_person", "japan")
INPUTS_FILE = "last_inputs"  # .meta_store/last_inputs.json: event lists of the last full build


class _NoNetwork:
    """Session stand-in for rebuilds from cache: any download attempt fails,
    so only events already in .meta_store are used."""

    def get(self, *args, **kwargs):
        raise RuntimeError("offline rebuild")


def build_meta_sheet(session=None, progress=lambda msg: None, use_weights=True, sources=ALL_SOURCES):
    global WEIGHTS
    WEIGHTS = current_weights()
    session = session or make_session()
    exp_en = fetch_expansions(session, "en")
    exp_jp = fetch_expansions(session, "jp") or exp_en
    oldest_era = len(WEIGHTS["era"]) - 1
    since_en = exp_en[oldest_era]["date"] if len(exp_en) > oldest_era else (date.today() - timedelta(days=180)).isoformat()
    since_jp = exp_jp[oldest_era]["date"] if len(exp_jp) > oldest_era else since_en

    progress("Listing tournaments…")
    in_person = [e for e in list_in_person(session) if e["date"] >= since_en]
    japan = [e for e in list_japan(session) if e["date"] >= since_jp]
    online = list_online(session, since_en)

    progress(f"Loading {len(online)} online, {len(in_person)} in-person and {len(japan)} Japanese events…")
    inperson_data = _fetch_all(session, fetch_in_person_event, in_person, "in-person", progress)
    standings_data = {d["event"]["id"]: d for d in
                      _fetch_all(session, fetch_in_person_standings, in_person, "in-person standings", progress)}
    labs_data = _fetch_labs(session, in_person, progress)
    japan_data = _fetch_all(session, fetch_japan_event, japan, "Japan", progress)
    online_data = _fetch_all(session, fetch_online_event, online, "online", progress)
    try:
        path = _store_path(INPUTS_FILE)
        with open(path + ".tmp", "w", encoding="utf-8") as handle:
            json.dump({"exp_en": exp_en, "exp_jp": exp_jp, "since_en": since_en, "since_jp": since_jp,
                       "in_person": in_person, "japan": japan, "online": online}, handle, ensure_ascii=False)
        os.replace(path + ".tmp", path)
    except Exception:
        pass
    return _assemble(exp_en, exp_jp, since_en, since_jp, inperson_data, standings_data, japan_data, online_data, labs_data,
                     use_weights, sources)


def rebuild_meta_sheet(use_weights=True, sources=ALL_SOURCES, progress=lambda msg: None):
    """The sheet from cached events only (no downloads), e.g. with weights off
    or one source. None if no full build has run yet."""
    global WEIGHTS
    WEIGHTS = current_weights()
    try:
        with open(_store_path(INPUTS_FILE), "r", encoding="utf-8") as handle:
            inputs = json.load(handle)
    except Exception:
        return None
    session = _NoNetwork()
    inperson_data = _fetch_all(session, fetch_in_person_event, inputs["in_person"], "in-person", progress)
    standings_data = {d["event"]["id"]: d for d in
                      _fetch_all(session, fetch_in_person_standings, inputs["in_person"], "in-person standings", progress)}
    labs_data = _fetch_labs(session, inputs["in_person"], progress)
    japan_data = _fetch_all(session, fetch_japan_event, inputs["japan"], "Japan", progress)
    online_data = _fetch_all(session, fetch_online_event, inputs["online"], "online", progress)
    return _assemble(inputs["exp_en"], inputs["exp_jp"], inputs["since_en"], inputs["since_jp"],
                     inperson_data, standings_data, japan_data, online_data, labs_data, use_weights, sources)


def _assemble(exp_en, exp_jp, since_en, since_jp, inperson_data, standings_data, japan_data, online_data,
              labs_data=None, use_weights=True, sources=ALL_SOURCES):
    sources = set(sources or ALL_SOURCES)

    def event_weight(kind, event, era):
        """Preferences weights, or 1 per event (inside the era window) when off."""
        w = _event_weight(kind, event, era)
        return w if use_weights else (1.0 if w > 0 else 0.0)

    archetypes = {}

    def arch(name, deck_id=None, icons=None, url=None):
        key = _key(name)
        a = archetypes.get(key)
        if a is None:
            a = archetypes[key] = {"id": key, "deck": name, "icons": [], "deck_url": None,
                                   "share_num": 0.0, "share_en_num": 0.0, "top_num": 0.0, "top_en_num": 0.0,
                                   "count": 0, "rw": 0, "rl": 0, "rt": 0, "mraw": {},
                                   "w": 0.0, "l": 0.0, "t": 0.0, "raw_games": 0, "ip_games": 0,
                                   # effective sample: Kish sums and per-pilot records (deck_score.py)
                                   "sw": 0.0, "sw2": 0.0, "pilots": [],
                                   "sources": {"online": 0, "in_person": 0, "japan": 0},
                                   "matchups": {},
                                   # in-person placings (raw counts + weighted for conversion)
                                   "ip": {"day2": 0, "top32": 0, "top8": 0, "wins": 0, "best": None,
                                          "w_day2": 0.0, "w_top32": 0.0, "w_top8": 0.0}}
        if icons and not a["icons"]:
            a["icons"] = list(icons)
        if url and not a["deck_url"]:
            a["deck_url"] = url
        return a

    # Icon signature -> archetype name (Japanese results only carry icons).
    icon_names = {}

    share_den = share_en_den = top_den = top_en_den = 0.0
    ip_totals = {"day2": 0.0, "top32": 0.0, "top8": 0.0}
    in_person_events = []
    events_used = {"online": 0, "in_person": 0, "japan": 0}
    in_person_records = 0  # in-person events with Labs match results

    for data in online_data:
        ev = data["event"]
        weight = event_weight("online", ev, era_of(ev["date"], exp_en))
        total = len(data["decks"])
        if weight <= 0 or not total:
            continue
        if "online" not in sources:
            for d in data["decks"]:
                arch(d["deck"], d["deck_id"], d["icons"],
                     f"https://play.limitlesstcg.com/decks/{d['deck_id']}?game=PTCG")
                if d["icons"]:
                    icon_names.setdefault(tuple(sorted(d["icons"])), d["deck"])
            continue
        events_used["online"] += 1
        share_den += weight
        share_en_den += weight
        seen = set()
        for d in data["decks"]:
            a = arch(d["deck"], d["deck_id"], d["icons"],
                     f"https://play.limitlesstcg.com/decks/{d['deck_id']}?game=PTCG")
            a["share_num"] += weight / total
            a["share_en_num"] += weight / total
            a["count"] += 1
            a["w"] += weight * d["w"]
            a["l"] += weight * d["l"]
            a["t"] += weight * d["t"]
            a["rw"] += d["w"]
            a["rl"] += d["l"]
            a["rt"] += d["t"]
            g = d["w"] + d["l"] + d["t"]
            a["raw_games"] += g
            a["sw"] += weight * g
            a["sw2"] += weight * weight * g
            if g:
                a["pilots"].append((d["w"] + 0.5 * d["t"], g))
            if d["icons"]:
                icon_names.setdefault(tuple(sorted(d["icons"])), d["deck"])
            if a["id"] not in seen:
                a["sources"]["online"] += 1
                seen.add(a["id"])
        for me, opps in data.get("matchups", {}).items():
            a = arch(me)
            for opp, (w, l, t) in opps.items():
                rec = a["matchups"].setdefault(_key(opp), [0.0, 0.0, 0.0])
                rec[0] += weight * w
                rec[1] += weight * l
                rec[2] += weight * t
                a["mraw"][_key(opp)] = a["mraw"].get(_key(opp), 0) + w + l + t

    # In-person names are sometimes shorter than the online ones ("Ogerpon
    # Meganium" vs "Ogerpon Meganium Hydrapple"). Map a name to the single
    # online archetype that contains those Pokemon, when exactly one does.
    online_sigs = {_pokemon_signature(a["deck"]): a["deck"] for a in archetypes.values()}

    def resolve_in_person(name):
        if _key(name) in archetypes:
            return name
        sig = _pokemon_signature(name)
        hits = [deck for s, deck in online_sigs.items() if sig and sig < s]
        return hits[0] if len(hits) == 1 else name

    for data in inperson_data:
        ev = data["event"]
        legal = (standings_data.get(ev["id"]) or {}).get("legal")
        era = era_of(ev["date"], exp_en, legal)
        weight = event_weight("in_person", ev, era)
        total = sum(d["count"] for d in data["decks"])
        points = sum(d["points"] for d in data["decks"]) or 1
        if weight <= 0 or not total:
            continue
        if "in_person" not in sources:
            for d in data["decks"]:
                arch(resolve_in_person(d["deck"]), d["deck_id"], d["icons"],
                     f"{LIMITLESS}/decks/{d['deck_id']}" if d.get("deck_id") else None)
                if d["icons"]:
                    icon_names.setdefault(tuple(sorted(d["icons"])), d["deck"])
            continue
        events_used["in_person"] += 1
        top_den += weight
        top_en_den += weight
        share_den += weight
        share_en_den += weight
        st = standings_data.get(ev["id"])
        placings = (st or {}).get("placings") or []
        winner = next((p["deck"] for p in placings if p["rank"] == 1), None)
        in_person_events.append({"id": ev["id"], "name": ev["name"], "date": ev["date"], "players": ev["players"],
                                 "winner": winner, "weight": round(weight, 2), "era": era,
                                 "legal": (st or {}).get("legal"), "url": f"{LIMITLESS}/tournaments/{ev['id']}"})
        for p in placings:
            ip = arch(resolve_in_person(p["deck"]))["ip"]
            ip["day2"] += 1
            ip["w_day2"] += weight
            ip_totals["day2"] += weight
            if p["rank"] <= 32:
                ip["top32"] += 1
                ip["w_top32"] += weight
                ip_totals["top32"] += weight
            if p["rank"] <= 8:
                ip["top8"] += 1
                ip["w_top8"] += weight
                ip_totals["top8"] += weight
            if p["rank"] == 1:
                ip["wins"] += 1
            if ip["best"] is None or p["rank"] < ip["best"]["rank"]:
                ip["best"] = {"rank": p["rank"], "event": ev["name"], "date": ev["date"]}
        # Match results from Limitless Labs (every round, whole field).
        labs = (labs_data or {}).get(ev["id"])
        if labs and labs.get("games"):
            in_person_records += 1
            name_of = {slug: resolve_in_person(d["name"]) for slug, d in labs["decks"].items()}
            for slug, (w, l, t) in labs["records"].items():
                a = arch(name_of.get(slug, slug), icons=labs["decks"].get(slug, {}).get("icons"))
                a["w"] += weight * w
                a["l"] += weight * l
                a["t"] += weight * t
                a["rw"] += w
                a["rl"] += l
                a["rt"] += t
                g = w + l + t
                a["raw_games"] += g
                a["ip_games"] += g
                a["sw"] += weight * g
                a["sw2"] += weight * weight * g
                a["pilots"] += [tuple(x) for x in labs["pilots"].get(slug, [])]
                for opp, (ow, ol, ot) in labs["matchups"].get(slug, {}).items():
                    cell = _key(name_of.get(opp, opp))
                    rec = a["matchups"].setdefault(cell, [0.0, 0.0, 0.0])
                    rec[0] += weight * ow
                    rec[1] += weight * ol
                    rec[2] += weight * ot
                    a["mraw"][cell] = a["mraw"].get(cell, 0) + ow + ol + ot
        for d in data["decks"]:
            a = arch(resolve_in_person(d["deck"]), d["deck_id"], d["icons"],
                     f"{LIMITLESS}/decks/{d['deck_id']}" if d.get("deck_id") else None)
            a["share_num"] += weight * d["count"] / total
            a["share_en_num"] += weight * d["count"] / total
            a["top_num"] += weight * d["points"] / points
            a["top_en_num"] += weight * d["points"] / points
            a["count"] += d["count"]
            a["sources"]["in_person"] += 1
            if d["icons"]:
                icon_names.setdefault(tuple(sorted(d["icons"])), d["deck"])

    # Pokemon-set -> best-known archetype name (most appearances wins).
    by_pokemon = {}
    for a in sorted(archetypes.values(), key=lambda x: x["count"]):
        by_pokemon[_pokemon_signature(a["deck"])] = a["deck"]

    for data in japan_data:
        ev = data["event"]
        weight = event_weight("japan", ev, era_of(ev["date"], exp_jp))
        placings = data["placings"]
        if weight <= 0 or not placings or "japan" not in sources:
            continue
        events_used["japan"] += 1
        top_den += weight
        share_den += weight
        # City League points: better placings earn more (16 -> 1).
        pts_total = sum(max(1, 17 - p["rank"]) for p in placings)
        seen = set()
        for p in placings:
            sig = tuple(sorted(p["icons"]))
            name = icon_names.get(sig)
            if not name:
                # Match by the Pokemon involved (ignoring Mega/ex) to an
                # archetype already known from online / in-person data.
                readable = _name_from_icons(p["icons"])
                # setdefault: Japan-only decks keep ONE name whatever order
                # their icons are listed in ("Ogerpon Mega Kangaskhan" ==
                # "Mega Kangaskhan Ogerpon").
                name = by_pokemon.setdefault(_pokemon_signature(readable), readable)
            a = arch(name, icons=p["icons"])
            a["share_num"] += weight / len(placings)
            a["top_num"] += weight * max(1, 17 - p["rank"]) / pts_total
            a["count"] += 1
            if a["id"] not in seen:
                a["sources"]["japan"] += 1
                seen.add(a["id"])

    # Games are clustered by pilot (one player plays 5-9 rounds with the same
    # list), so they are not independent coin flips. Estimate the spread of
    # pilot win rates within an archetype (tau^2, method of moments, pooled over
    # all archetypes) and the resulting design effect per archetype. The
    # effective sample = Kish's weighted n / design effect.
    num = den = 0.0
    for a in archetypes.values():
        n_tot = sum(n for _x, n in a["pilots"])
        if n_tot < 20:
            continue
        p = sum(x for x, _n in a["pilots"]) / n_tot
        var = p * (1.0 - p)
        for x, n in a["pilots"]:
            num += (x - n * p) ** 2 - n * var
            den += n * (n - 1.0)
    pilot_var = max(0.0, num / den) if den else 0.0

    def effective_games(a):
        if a["sw2"] <= 0:
            return 0.0
        kish = a["sw"] * a["sw"] / a["sw2"]
        n_tot = sum(n for _x, n in a["pilots"])
        if not n_tot:
            return kish
        p = min(0.95, max(0.05, sum(x for x, _n in a["pilots"]) / n_tot))
        cluster = sum(n * (n - 1.0) for _x, n in a["pilots"]) / n_tot
        design = 1.0 + pilot_var / (p * (1.0 - p)) * cluster
        return kish / design

    def on_real_games(rec, games):
        """Weights decide how much each game counts, never how many games
        there are: the weighted W/L/T proportions, scaled to the real games."""
        total = sum(rec)
        return [x * games / total for x in rec] if total > 0 else [0.0, 0.0, 0.0]

    rows = []
    for a in archetypes.values():
        share = 100.0 * a["share_num"] / share_den if share_den else 0.0
        w_rec = on_real_games((a["w"], a["l"], a["t"]), a["raw_games"])
        if share < 0.05 and not a["raw_games"]:
            continue
        games = sum(w_rec)
        post = win_rate_posterior(*w_rec) if games else None
        rows.append({
            "id": a["id"],
            "deck": a["deck"],
            "icons": a["icons"],
            "deck_url": a["deck_url"],
            "count": a["count"],
            "share": round(share, 2),
            # English-legal field only (no Japan-only decks): what the ladder faces.
            "share_en": round(100.0 * a["share_en_num"] / share_en_den, 2) if share_en_den else 0.0,
            "top_share": round(100.0 * a["top_num"] / top_den, 2) if top_den else None,
            # Top finishes in the English field only (in-person), to compare with share_en.
            "top_share_en": round(100.0 * a["top_en_num"] / top_en_den, 2) if top_en_den else None,
            # Actual games played (the W/L/T above are event-weighted sums).
            "raw_wins": a["rw"], "raw_losses": a["rl"], "raw_ties": a["rt"],
            # Weighted record on the real number of games (sums to raw_games):
            # the win rate the deck pages compare against.
            "wins": round(w_rec[0], 1),
            "losses": round(w_rec[1], 1),
            "ties": round(w_rec[2], 1),
            "raw_games": a["raw_games"],
            "ip_games": a["ip_games"],  # of which in-person (Limitless Labs pairings)
            "eff_games": round(effective_games(a), 1),
            "win_pct": round(post["observed"] * 100.0, 1) if post and post["observed"] is not None else None,
            "bayes_win_pct": round(post["mean"] * 100.0, 1) if post else None,
            "sources": a["sources"],
            "matchups": {k: [round(x, 2) for x in on_real_games(v, a["mraw"].get(k, 0))]
                         for k, v in a["matchups"].items() if a["mraw"].get(k)},
            "in_person": _in_person_summary(a["ip"], ip_totals),
            "record_source": "unified",
        })
    rows.sort(key=lambda r: r["share"], reverse=True)
    sheet = {
        "schema_version": SCHEMA_VERSION,
        # wins/losses/ties and matchups = weighted proportions x real games
        "record_basis": "real_games",
        "rows": rows,
        "fetched_at": time.time(),
        "events": events_used,
        "in_person_records": in_person_records,
        "tournaments_processed": sum(events_used.values()),
        "total_entries": sum(int(d["event"].get("players") or 0) for d in online_data)
                         + sum(int(e.get("players") or 0) for e in in_person_events),
        "in_person_events": sorted(in_person_events, key=lambda e: e["date"], reverse=True),
        "expansions": {"en": exp_en[:4], "jp": exp_jp[:4]},
        "weights": WEIGHTS,
        # sd of pilot win rates within an archetype (pilot skill + luck of the
        # draw beyond binomial noise); used as the prior spread for YOUR decks.
        "pilot_sd": round(pilot_var ** 0.5, 4),
        "view": {"use_weights": bool(use_weights), "sources": sorted(sources)},
        "window": {"en_since": since_en, "jp_since": since_jp},
    }
    return sheet


if __name__ == "__main__":
    t0 = time.time()
    sheet = build_meta_sheet(progress=print)
    with open(SHEET_FILE, "w", encoding="utf-8") as handle:
        json.dump(sheet, handle, ensure_ascii=False)
    print(f"built in {time.time() - t0:.0f}s: events {sheet['events']}, {len(sheet['rows'])} archetypes")
    print("current expansion (EN):", sheet["expansions"]["en"][:1], " JP:", sheet["expansions"]["jp"][:1])
    for r in sheet["rows"][:15]:
        print(f"  {r['deck']:<28} share {r['share']:5.2f}%  top {r['top_share'] or 0:5.2f}%  "
              f"WR {r['win_pct'] if r['win_pct'] is not None else '--':>5}  games {r['raw_games']:>5}  src {r['sources']}")
    os._exit(0)  # don't wait on any abandoned (timed-out) download threads
