"""
Your own decklists, captured from Pokemon TCG Live's deck export.

In PTCGL: Decks → (deck) → Export → "Copy to clipboard". The monitor sees the
list on the clipboard and stores it here - every different list (same cards =
same list), named from its cards (renameable),
so the In Person tab can print it via pokedata.ovh/paper without retyping.

Export format:
    Pokémon: 15
    4 Dreepy TWM 128
    ...
    Trainer: 35
    ...
    Energy: 10
    ...
    Total Cards: 60
"""

import json
import os
import re
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_FILE = os.path.join(BASE_DIR, ".decklists.json")

_SECTION = re.compile(r"^(Pok[eé]mon|Trainer|Energy)\s*:\s*\d+\s*$", re.IGNORECASE | re.MULTILINE)
_CARD = re.compile(r"^\d+\s+.+\s+[A-Za-z0-9-]{2,6}\s+[A-Za-z0-9-]+\s*$", re.MULTILINE)


def is_ptcgl_decklist(text):
    """True for a PTCGL deck export (sections + card lines, ~60 cards)."""
    if not text or len(text) > 20000:
        return False
    if len(_SECTION.findall(text)) < 2 or len(_CARD.findall(text)) < 5:
        return False
    total = sum(int(line.split()[0]) for line in _CARD.findall(text))
    return 40 <= total <= 70


def card_count(text):
    return sum(int(line.split()[0]) for line in _CARD.findall(text or ""))


def _load():
    """{"lists": [entry, ...]} (newest first). Older files kept one list per
    OCR deck name ("by_deck"); they're converted on read."""
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {"lists": []}
    if not isinstance(data, dict):
        return {"lists": []}
    if "lists" in data and not isinstance(data["lists"], list):
        data["lists"] = []
    if "lists" not in data:
        old = list((data.get("by_deck") or {}).values())
        if not old and data.get("latest"):
            old = [data["latest"]]
        data = {"lists": []}
        for entry in old:
            text = entry.get("text") or ""
            if text:
                data["lists"].append({"id": list_id(text), "name": entry.get("deck") or auto_name(text),
                                      "text": text, "cards": card_count(text),
                                      "captured_at": entry.get("captured_at", ""), "named_by": "ocr"})
    return data


def _save(data):
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, STORE_FILE)


def _cards(text):
    """{card line without count: total count} - order and duplicates ignored."""
    cards = {}
    for line in _CARD.findall(text or ""):
        count, rest = line.split(None, 1)
        key = " ".join(rest.split())
        cards[key] = cards.get(key, 0) + int(count)
    return cards


def list_id(text):
    """Same cards (in any order / split over lines) = same list."""
    import hashlib
    canon = "\n".join(f"{n} {c}" for c, n in sorted(_cards(text).items()))
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()[:12]


def auto_name(text):
    """A readable name from the list itself: its main Pokemon (the most
    copies of a rule-box Pokemon, else of any Pokemon), plus a partner."""
    section = re.split(r"^\s*Trainer\s*:", text or "", flags=re.IGNORECASE | re.MULTILINE)[0]
    totals = {}
    for line in _CARD.findall(section):
        count, rest = line.split(None, 1)
        name = re.sub(r"\s+[A-Za-z0-9-]{2,6}\s+[A-Za-z0-9-]+\s*$", "", rest).strip()
        totals[name] = totals.get(name, 0) + int(count)
    if not totals:
        return "Decklist"
    def rank(item):
        name, count = item
        rule_box = bool(re.search(r"\b(ex|V|VSTAR|VMAX|GX)\b", name))
        return (rule_box, count)
    ordered = sorted(totals.items(), key=rank, reverse=True)
    main = ordered[0][0]
    partner = next((n for n, c in ordered[1:] if c >= 2 and re.search(r"\b(ex|V|VSTAR|VMAX)\b", n)
                    and n.split()[0] != main.split()[0]), None)
    return f"{main} / {partner}" if partner else main


def save_decklist(text, deck_name=None):
    """Store an exported list. A list with the same cards updates its
    timestamp (and keeps its name); a new list is added with a name made
    from its cards (deck_name, the deck last seen on the main menu, is only
    a hint: PTCGL's export doesn't say which deck it is).
    Returns the entry plus "new": True/False."""
    data = _load()
    lid = list_id(text)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = next((e for e in data["lists"] if e["id"] == lid), None)
    is_new = entry is None
    if is_new:
        name = auto_name(text)
        taken = {e["name"] for e in data["lists"]}
        base, n = name, 2
        while name in taken:
            name, n = f"{base} ({n})", n + 1
        entry = {"id": lid, "name": name, "text": text.strip(), "cards": card_count(text),
                 "captured_at": now, "named_by": "auto", "menu_deck": deck_name}
        data["lists"].insert(0, entry)
    else:
        entry["captured_at"] = now
        data["lists"].remove(entry)
        data["lists"].insert(0, entry)  # newest first
    _save(data)
    return dict(entry, new=is_new, deck=entry["name"])


def rename_decklist(lid, name):
    data = _load()
    for entry in data["lists"]:
        if entry["id"] == lid and name.strip():
            entry["name"] = name.strip()
            entry["named_by"] = "user"
    _save(data)


def delete_decklist(lid):
    data = _load()
    data["lists"] = [e for e in data["lists"] if e["id"] != lid]
    _save(data)


def all_decklists():
    """Every stored list, newest export first."""
    return _load()["lists"]


def store_mtime():
    try:
        return os.path.getmtime(STORE_FILE)
    except OSError:
        return None


# ── deck <-> list links (Deck Snapshot "Decklist" button) ──
def link_decklist(deck_name, lid):
    """Remember which stored list is `deck_name` (the deck name on the menu).
    lid None removes the link."""
    data = _load()
    links = data.setdefault("links", {})
    if (data.get("auto_links") or {}).pop(deck_name, None) and not lid:
        data.setdefault("auto_off", []).append(deck_name)  # unlinked an auto list: don't capture again
    if lid:
        links[deck_name] = lid
    else:
        links.pop(deck_name, None)
    _save(data)


def decklist_for_deck(deck_name):
    """The list linked to a deck, else the newest list exported while that
    deck was on the menu, else None."""
    data = _load()
    lists = data.get("lists") or []
    lid = (data.get("links") or {}).get(deck_name)
    entry = next((e for e in lists if e["id"] == lid), None) if lid else None
    if entry is None:
        entry = next((e for e in lists if e.get("menu_deck") == deck_name), None)
    return entry


def import_decklist(text, deck_name):
    """Store a pasted PTCGL export and link it to `deck_name`."""
    entry = save_decklist(text, deck_name)
    link_decklist(deck_name, entry["id"])
    return entry


# ── auto-capture: a list built from the cards you showed in your games ──
def is_auto_linked(deck_name):
    """True when the deck's link was made by auto_capture (not by you)."""
    data = _load()
    lid = (data.get("links") or {}).get(deck_name)
    return bool(lid) and (data.get("auto_links") or {}).get(deck_name) == lid


def auto_capture(deck_name, text, games=0):
    """Store `text` (a full 60-card list made from your games) and link it to
    `deck_name`, marked as auto-captured. Never replaces a list you linked or
    exported for that deck, nor a deck whose auto list you unlinked; a
    previous auto-captured list is replaced. Returns the entry or None."""
    if not deck_name or not text:
        return None
    data = _load()
    lists = data.setdefault("lists", [])
    links = data.setdefault("links", {})
    auto = data.setdefault("auto_links", {})
    if deck_name in (data.get("auto_off") or []):
        return None
    if deck_name in links and auto.get(deck_name) != links[deck_name]:
        return None  # your own link
    if deck_name not in links and any(e.get("menu_deck") == deck_name or
                                      (e.get("name") == deck_name and e.get("named_by") == "ocr") for e in lists):
        return None  # you exported this deck's list (older stores named it after the deck)
    lid = list_id(text)
    old = auto.get(deck_name)
    if old == lid:
        return next((e for e in lists if e["id"] == lid), None)
    if old and old not in [v for k, v in links.items() if k != deck_name]:
        lists[:] = [e for e in lists if not (e["id"] == old and e.get("auto_captured"))]
    entry = next((e for e in lists if e["id"] == lid), None)
    if entry is None:
        name = f"{deck_name} (auto)"
        taken = {e["name"] for e in lists}
        base, n = name, 2
        while name in taken:
            name, n = f"{base[:-1]} {n})", n + 1
        entry = {"id": lid, "name": name, "text": text.strip(), "cards": card_count(text),
                 "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"), "named_by": "auto",
                 "menu_deck": None, "auto_captured": {"deck": deck_name, "games": int(games)}}
        lists.insert(0, entry)
    links[deck_name] = lid
    auto[deck_name] = lid
    _save(data)
    return entry


def _resolve_log(path):
    if not path:
        return None
    if os.path.isabs(path) and os.path.exists(path):
        return path
    rel = path.replace("\\", "/").lstrip("/")
    for candidate in (os.path.join(BASE_DIR, rel), os.path.join(BASE_DIR, "Logs", os.path.basename(rel))):
        if os.path.exists(candidate):
            return candidate
    return None


def seen_in_games(deck_name, username, db_path=None, rows=None):
    """card_usage.merge_seen over your games with `deck_name` (newest first),
    from the battle logs in the database. Adds "logs": games with a readable log."""
    import sqlite3
    import card_usage
    from AIParseBattleLog import load_meta_rows, parse_opponent_from_log, read_battlelog_file
    rows = rows if rows is not None else load_meta_rows()
    card_usage.set_known_cards(c["name"] for r in rows for c in r.get("cards") or [])
    conn = sqlite3.connect(db_path or os.path.join(BASE_DIR, "tcg_battles.db"))
    try:
        paths = [p for (p,) in conn.execute(
            "SELECT log_file FROM battles WHERE my_deck = ? ORDER BY timestamp DESC, id DESC", (deck_name,))]
    finally:
        conn.close()
    games = []
    for path in paths:
        text = read_battlelog_file(_resolve_log(path))
        if text:
            opponent = parse_opponent_from_log(text, username)
            games.append(card_usage.log_deck_counts(text, username, opponent))
    result = card_usage.merge_seen(games)
    result["logs"] = len(games)
    return result


def capture_from_games(deck_name, username, db_path=None, rows=None, store=True):
    """After a battle: when your games with `deck_name` have shown all 60
    cards and the deck has no list linked, save and link the list made from
    them (auto_capture). Returns the merge_seen result plus "text",
    "missing" (cards with no known print) and "entry" (the stored list)."""
    import card_usage
    if not deck_name or not username:
        return None
    if rows is None:
        from AIParseBattleLog import load_meta_rows
        rows = load_meta_rows()
    result = seen_in_games(deck_name, username, db_path, rows)
    result.update(text=None, missing=[], entry=None)
    if result["complete"]:
        prints = card_usage.card_prints(rows, [e.get("text") for e in all_decklists()])
        result["text"], result["missing"] = card_usage.format_list(result["cards"], prints)
        if result["text"] and store:
            result["entry"] = auto_capture(deck_name, result["text"], result["games"])
    return result
