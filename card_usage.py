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
    """One spelling for every source: PTCGL exports "Basic {D} Energy" and
    battle logs "Basic Darkness Energy" = Limitless "Darkness Energy";
    "Shadowy {D} Energy" = "Shadowy Darkness Energy"; curly quotes = straight."""
    name = " ".join((name or "").replace("’", "'").split())
    m = re.fullmatch(r"Basic \{(\w)\} Energy", name)
    if m:
        return f"{ENERGY_TYPES.get(m.group(1), m.group(1))} Energy"
    m = re.fullmatch(r"Basic (\w+) Energy", name)
    if m and m.group(1) in ENERGY_TYPES.values():
        return f"{m.group(1)} Energy"
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


# ── Opponent's deck from the cards in a battle log ────────────────────────
def log_cards(battlelog, player, other=None):
    """Distinct card names `player` revealed in a PTCGL battle log: cards
    played, benched, attached, evolved, searched or shown (mulligans), and
    the bullet lists under their lines. Text after the other player's name
    (targets: "... on Sanchomr's Smoochum") isn't theirs, so it's cut."""
    if not battlelog or not player:
        return set()
    known = _known_card_pattern()
    seen, actor = set(), None
    for raw in battlelog.splitlines():
        line = raw.strip().replace("’", "'")
        if not line:
            continue
        if line.startswith("•"):
            if actor == player:
                for item in line.lstrip("• ").split(","):
                    name = card_name(item)
                    # card lists only, not "Base damage: 130 damage" breakdowns
                    if name and ":" not in name and not re.search(r"\d", name):
                        seen.add(name)
            continue
        body = line[2:] if line.startswith("- ") else line
        if body.startswith(player):
            actor = player
            text = body[len(player):]
            if other and other in text:
                text = text[:text.index(other)]
            if known is not None:
                seen.update(card_name(m) for m in known.findall(text))
        elif other and body.startswith(other):
            actor = other
        elif not line.startswith("- "):
            actor = None
    return seen


_PATTERN = {"names": None, "regex": None}


def set_known_cards(names):
    """Card names to look for in log lines (longest first, whole words)."""
    names = sorted({n for n in names if n and len(n) > 2}, key=len, reverse=True)
    if names != _PATTERN["names"]:
        _PATTERN["names"] = names
        alt = "|".join(re.escape(n).replace("\ ", r"\s+") for n in names)
        _PATTERN["regex"] = re.compile(rf"(?<![\w'])({alt})(?![\w'])") if names else None


def _known_card_pattern():
    return _PATTERN["regex"]


def classify(cards_seen, rows, top=3, floor=0.004):
    """Rank meta archetypes by how well their decklists explain the cards
    seen: log P(deck) + sum over seen cards of log P(card in a list of that
    deck). A card the archetype never plays counts as `floor` (0.4% of
    lists), so one odd tech doesn't rule a deck out. Cards that every deck
    plays barely move the ranking. Returns [(row, probability)], best first,
    or [] when no Pokémon card was seen."""
    import math
    seen = set(cards_seen or ())
    candidates = [r for r in rows if r.get("cards") and r.get("lists", 0) >= 5]
    if not seen or not candidates:
        return []
    pokemon = {c["name"] for r in candidates for c in r["cards"] if c["cat"] == "P"}
    if not seen & pokemon:
        return []
    total_share = sum(r.get("share_en") or r.get("share") or 0.0 for r in candidates) or 1.0
    scored = []
    for r in candidates:
        incl = {c["name"]: c["incl"] / 100.0 for c in r["cards"]}
        prior = max(1e-4, (r.get("share_en") or r.get("share") or 0.0) / total_share)
        score = math.log(prior)
        for name in seen:
            p = incl.get(name)
            if p is None and name not in pokemon:
                continue  # a trainer/energy outside every top list says little
            score += math.log(max(floor, min(0.999, p or 0.0)))
        scored.append((score, r))
    scored.sort(key=lambda s: -s[0])
    best = scored[0][0]
    weights = [math.exp(s - best) for s, _r in scored]
    norm = sum(weights)
    return [(r, w / norm) for (_s, r), w in list(zip(scored, weights))[:top]]
