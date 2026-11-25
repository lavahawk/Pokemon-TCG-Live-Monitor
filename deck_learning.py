"""
Deck corrections: what the app guessed for a battle's opponent deck when you
changed it to something else. Both detectors learn from them:

  no AI   local_model.LocalModel remembers every game whose deck you set
          yourself (on the overlay card or in the battle table) by the cards
          the opponent showed, and leans toward that deck when a new game
          shows the same cards, and away from the guess you corrected.
  AI      the same memory checks the AI's answer (a near-identical corrected
          game wins), and for your own AI key or local model the prompt
          lists the closest corrected games.

The store is only {battle log hash: the rejected guess}; the deck you picked
and the cards come from the database and the logs (local_model's cache), so a
later edit or a deleted battle needs nothing here.

    .deck_corrections.json  {"version": 1, "rejected": {log_hash: {"deck", "source", "at"}}}
"""

import json
import os
import re
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_FILE = os.path.join(BASE_DIR, ".deck_corrections.json")
MAX_ENTRIES = 5000


def _norm(name):
    return " ".join(str(name or "").split())


def _load():
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("rejected"), dict):
            return data
    except Exception:
        pass
    return {"version": 1, "rejected": {}}


def _save(data):
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)
    os.replace(tmp, STORE_FILE)


def usable(name):
    key = _norm(name).casefold()
    return bool(key) and not key.startswith("unknown") and key not in ("other", "none")


def record(log_hash, guessed, chosen, source=None):
    """You changed a battle's opponent deck from `guessed` to `chosen`.
    Kept only when it's a real correction (a different deck)."""
    if not log_hash or not usable(guessed) or _norm(guessed).casefold() == _norm(chosen).casefold():
        return False
    try:
        data = _load()
        rejected = data["rejected"]
        if log_hash in rejected:
            return False  # the first guess is the one that was wrong
        rejected[log_hash] = {"deck": _norm(guessed), "source": source or "", "at": time.time()}
        if len(rejected) > MAX_ENTRIES:
            for old in sorted(rejected, key=lambda h: rejected[h].get("at") or 0)[:len(rejected) - MAX_ENTRIES]:
                rejected.pop(old, None)
        _save(data)
        return True
    except Exception:
        return False


def rejected_by_hash():
    """{log_hash: the guess you corrected}."""
    return {h: e.get("deck") for h, e in _load()["rejected"].items() if usable(e.get("deck"))}


def count():
    return len(_load()["rejected"])


# ── one spelling for every deck ──────────────────────────────────────────
_FILLER = {"ex", "deck", "box", "and", "with", "the", "/", "&", "+"}


def word_key(name):
    """"Dragapult ex", "dragapult" and "Dragapult  EX" are one deck;
    "Dusknoir Dragapult" is "Dragapult Dusknoir"."""
    words = re.findall(r"[a-z0-9'à-ɏ.-]+", _norm(name).casefold())
    return frozenset(w for w in words if w not in _FILLER)


def canonical_deck(name, names):
    """`name` in the spelling the app already uses for that deck (the first
    of `names` that matches, so list the meta sheet's names first), else
    `name` itself. AI picks, local guesses and typed names all end up as one
    deck in the stats this way."""
    name = _norm(name)
    if not name:
        return name
    key = name.casefold()
    names = [_norm(n) for n in names or () if _norm(n)]
    for known in names:
        if known.casefold() == key:
            return known
    words = word_key(name)
    if words:
        for known in names:
            if word_key(known) == words:
                return known
    return name
