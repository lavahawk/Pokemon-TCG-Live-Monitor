"""
Card usage of meta archetypes vs your own decklists (no Qt).

The meta sheet (meta_sources.py) carries, per archetype, the cards played in
its public decklists: incl (% of lists), avg (copies when played), per_list
(copies per list overall). This module reads your PTCGL exports
(decklists.py), puts both on the same card names and compares them.
"""

import re

ENERGY_TYPES = {"G": "Grass", "R": "Fire", "W": "Water", "L": "Lightning", "P": "Psychic",
                "F": "Fighting", "D": "Darkness", "M": "Metal", "Y": "Fairy", "N": "Dragon", "C": "Colorless"}
CATS = {"pokémon": "P", "pokemon": "P", "trainer": "T", "energy": "E"}
CAT_NAMES = {"P": "Pokémon", "T": "Trainer", "E": "Energy"}

CORE, COMMON = 90.0, 50.0  # % of lists: core card / common choice / tech


def card_name(name):
    """One spelling for both sources: PTCGL "Basic {D} Energy" = Limitless
    "Darkness Energy", "Shadowy {D} Energy" = "Shadowy Darkness Energy"."""
    name = " ".join((name or "").split())
    m = re.fullmatch(r"Basic \{(\w)\} Energy", name)
    if m:
        return f"{ENERGY_TYPES.get(m.group(1), m.group(1))} Energy"
    return re.sub(r"\{(\w)\}", lambda t: ENERGY_TYPES.get(t.group(1), t.group(1)), name)


def parse_list(text):
    """PTCGL export -> {(cat, name): copies}; prints of the same card merged."""
    cards, cat = {}, "P"
    for line in (text or "").splitlines():
        line = line.strip()
        head = re.match(r"(Pok[eé]mon|Trainer|Energy)\s*:\s*\d+$", line, re.IGNORECASE)
        if head:
            cat = "P" if head.group(1).lower().startswith("pok") else CATS[head.group(1).lower()]
            continue
        m = re.match(r"(\d+)\s+(.+?)\s+[A-Za-z0-9-]{2,6}\s+[A-Za-z0-9-]+$", line)
        if m:
            key = (cat, card_name(m.group(2)))
            cards[key] = cards.get(key, 0) + int(m.group(1))
    return cards


def similarity(meta_cards, mine):
    """How much of your list matches an archetype's typical list (0-1):
    shared copies / max(60, ...), with the archetype's copies per list."""
    if not meta_cards or not mine:
        return 0.0
    typical = {(c["cat"], c["name"]): c["per_list"] for c in meta_cards}
    shared = sum(min(n, typical.get(k, 0.0)) for k, n in mine.items())
    return shared / max(60.0, float(sum(mine.values())))


def best_archetype(rows, mine, minimum=0.35):
    """The meta row whose typical list is closest to yours, or None."""
    best, score = None, minimum
    for row in rows:
        s = similarity(row.get("cards"), mine)
        if s > score:
            best, score = row, s
    return best


def role(incl):
    return "core" if incl >= CORE else "common" if incl >= COMMON else "tech"


def compare(meta_cards, mine=None):
    """Table rows: every archetype card (most played first), then cards only
    in your list. Each: {cat, name, set, number, incl, avg, typical, mine,
    diff, role}. typical = usual copies (avg rounded) when the card is played
    in at least half the lists, else 0."""
    mine = dict(mine) if mine is not None else None  # None = no list chosen
    out = []
    for c in meta_cards or []:
        key = (c["cat"], c["name"])
        typical = int(round(c["avg"])) if c["incl"] >= COMMON else 0
        have = mine.pop(key, 0) if mine is not None else None
        out.append({"cat": c["cat"], "name": c["name"], "set": c.get("set"), "number": c.get("number"),
                    "incl": c["incl"], "avg": c["avg"], "typical": typical, "mine": have,
                    "diff": (have - typical) if have is not None else None, "role": role(c["incl"])})
    for (cat, name), have in sorted((mine or {}).items(), key=lambda kv: (kv[0][0] != "P", kv[0][0], kv[0][1])):
        out.append({"cat": cat, "name": name, "set": None, "number": None, "incl": 0.0, "avg": 0.0,
                    "typical": 0, "mine": have, "diff": have, "role": "only yours"})
    return out


def summary(rows):
    """Counts for the header line: core cards you're missing, extra techs."""
    missing = [r for r in rows if r["role"] == "core" and r["mine"] == 0]
    unusual = [r for r in rows if r["mine"] and r["incl"] < 10.0]
    return {"core": sum(1 for r in rows if r["role"] == "core"), "missing_core": missing, "unusual": unusual}
