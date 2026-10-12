"""
Your own decklists, captured from Pokemon TCG Live's deck export.

In PTCGL: Decks → (deck) → Export → "Copy to clipboard". The monitor sees the
list on the clipboard and stores it here (per deck name, plus the latest one),
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
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_decklist(text, deck_name=None):
    data = _load()
    entry = {"deck": deck_name or "Unknown deck", "text": text.strip(),
             "cards": card_count(text), "captured_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    data["latest"] = entry
    data.setdefault("by_deck", {})[entry["deck"]] = entry
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, STORE_FILE)
    return entry


def latest_decklist():
    return _load().get("latest")


def all_decklists():
    return _load().get("by_deck", {})
