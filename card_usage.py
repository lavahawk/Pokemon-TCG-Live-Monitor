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
    return set(log_card_counts(battlelog, player, other))


MAX_COPIES = 4


def log_card_counts(battlelog, player, other=None, cap=MAX_COPIES):
    """{card: copies seen} for `player`: how many times each card was put
    into play (benched / played to the Active Spot / evolved into / played as
    a Trainer / attached), capped at `cap` (4; None = no cap). Cards only shown (mulligan, search,
    discard) count 1. A lower bound, apart from cards recycled and replayed:
    "4 Gengar ex seen" says Gengar deck, "1 Zoroark ex" says a tech."""
    if not battlelog or not player:
        return {}
    known = _known_card_pattern()
    counts, actor, bench_list = {}, None, False

    def add(name, n=1):
        if name and ":" not in name and not re.search(r"\d", name):
            counts[name] = max(counts.get(name, 0), 0) + n

    def shown(name):
        if name and ":" not in name and not re.search(r"\d", name):
            counts.setdefault(name, 0)

    for raw in battlelog.splitlines():
        line = raw.strip().replace("’", "'")
        if not line:
            continue
        if line.startswith("•"):
            if actor == player:
                for item in line.lstrip("• ").split(","):
                    name = card_name(item)
                    (add if bench_list else shown)(name)  # "drew 2 cards and played them to the Bench"
            continue
        body = line[2:] if line.startswith("- ") else line
        if body.startswith(player):
            actor = player
            text = body[len(player):]
            if other and other in text:
                text = text[:text.index(other)]
            bench_list = "played them to the Bench" in text
            evolved = re.match(r"\s+evolved (.+?) to (.+?)(?: in the | on the |\.?$)", text)
            played = re.match(r"\s+(?:played|attached) (.+?)(?: to | in the |\.?$)", text)
            if evolved:
                add(card_name(evolved.group(2)))
                shown(card_name(evolved.group(1)))
            elif played:
                add(card_name(played.group(1)))
            if known is not None:
                # Only the subject part: after " to " / " on " / " from " come
                # targets, and PTCGL sometimes prefixes those with the wrong
                # owner ("moved damage counters ... to <opp>'s Mega Gengar ex").
                for m in known.findall(re.split(r" (?:to|on|from|onto|with) ", text)[0]):
                    shown(card_name(m))
        elif other and body.startswith(other):
            actor, bench_list = other, False
        elif not line.startswith("- "):
            actor, bench_list = None, False
    return {name: min(cap or n or 1, max(1, n)) for name, n in counts.items()}


_PATTERN = {"names": None, "regex": None}


def set_known_cards(names):
    """Card names to look for in log lines (longest first, whole words)."""
    names = sorted({n for n in names if n and len(n) > 2}, key=len, reverse=True)
    if names != _PATTERN["names"]:
        _PATTERN["names"] = names
        alt = "|".join(re.escape(n).replace(r"\ ", r"\s+") for n in names)
        _PATTERN["regex"] = re.compile(rf"(?<![\w'])({alt})(?![\w'])") if names else None


def _known_card_pattern():
    return _PATTERN["regex"]


CLOSE_CALL = 2 / 3     # top pick below this = a close call ...
CLOSE_CONTENDER = 0.25  # ... decided by popularity among picks at least this likely


def popularity(row):
    """% of today's field: the last weeks of online (PTCGL) events, else the
    whole-window English share."""
    recent = row.get("share_recent")
    return recent if recent is not None else (row.get("share_en") or row.get("share") or 0.0)


def classify(cards_seen, rows, top=3, floor=0.004):
    """Rank meta archetypes by how well their decklists explain the cards
    seen: log P(deck) + sum over seen cards of log P(card in a list of that
    deck). A card the archetype never plays counts as `floor` (0.4% of
    lists), so one odd tech doesn't rule a deck out. Cards that every deck
    plays barely move the ranking.

    cards_seen may be {card: copies seen} (log_card_counts): seeing more
    copies than the archetype usually plays costs e^-2 per extra copy, so 4
    Zoroark ex point to a Zoroark deck, 1 fits a Gengar deck's tech.
    Returns [(row, probability)], best first, or [] when no Pokémon card
    was seen."""
    import math
    copies = dict(cards_seen) if isinstance(cards_seen, dict) else {c: 1 for c in cards_seen or ()}
    seen = set(copies)
    candidates = [r for r in rows if r.get("cards") and r.get("lists", 0) >= 5]
    if not seen or not candidates:
        return []
    pokemon = {c["name"] for r in candidates for c in r["cards"] if c["cat"] == "P"}
    if not seen & pokemon:
        return []
    total_share = sum(popularity(r) for r in candidates) or 1.0
    scored = []
    for r in candidates:
        incl = {c["name"]: c["incl"] / 100.0 for c in r["cards"]}
        avg = {c["name"]: c.get("avg") or 1.0 for c in r["cards"]}
        prior = max(1e-4, popularity(r) / total_share)
        score = math.log(prior)
        for name in seen:
            p = incl.get(name)
            if p is None and name not in pokemon:
                continue  # a trainer/energy outside every top list says little
            score += math.log(max(floor, min(0.999, p or 0.0)))
            k = copies.get(name, 1)
            if p and k > avg[name] + 0.5 and not name.endswith(" Energy"):
                # More copies than this deck plays: each extra copy beyond the
                # usual count (+0.5 slack for a recovered card played again)
                # costs e^-2 (4 Zorua seen vs ~2 in a Gengar list ≈ 0.07).
                score -= 2.0 * (k - avg[name] - 0.5)
        scored.append((score, r))
    scored.sort(key=lambda s: -s[0])
    best = scored[0][0]
    weights = [math.exp(s - best) for s, _r in scored]
    norm = sum(weights)
    ranked = [(r, w / norm) for (_s, r), w in list(zip(scored, weights))[:top]]
    # Close call: the most popular contender is the better bet (it's met far
    # more often). Probabilities stay as computed; only the order changes.
    if ranked[0][1] < CLOSE_CALL:
        contenders = [x for x in ranked if x[1] >= CLOSE_CONTENDER]
        # No contender at all (top pick under CLOSE_CONTENDER): keep the order.
        # max() of an empty list raised here and the parser lost the evidence.
        best_pop = max(contenders, key=lambda x: popularity(x[0])) if contenders else ranked[0]
        if best_pop is not ranked[0]:
            ranked.remove(best_pop)
            ranked.insert(0, best_pop)
    return ranked


def explain(ranked, copies, rows, max_fit=4, max_odd=3):
    """Compact evidence for the AI parser (a few lines, ~150 tokens): the
    opponent's Pokémon with copies seen, then each candidate archetype with
    the revealed cards that fit its usual list best (share of lists, usual
    copies) and the ones that are odd for it."""
    if not ranked:
        return ""
    pokemon = {c["name"] for r in rows for c in r.get("cards") or [] if c["cat"] == "P"}
    seen_p = sorted((n for n in copies if n in pokemon), key=lambda n: (-copies[n], n))
    lines = ["Opponent revealed (copies seen): " + ", ".join(f"{n} x{copies[n]}" for n in seen_p)]
    profiles = {r["deck"]: {c["name"]: c for c in r.get("cards") or []} for r, _p in ranked}
    for i, (r, prob) in enumerate(ranked, 1):
        mine = profiles[r["deck"]]
        others = [profiles[o["deck"]] for o, _p in ranked if o is not r]

        def lift(name):
            here = mine[name]["incl"]
            return here - max((o[name]["incl"] if name in o else 0.0) for o in others) if others else here
        # Pokémon first (they name decks), then the most telling Trainers.
        fits = sorted((n for n in copies if n in mine and mine[n]["incl"] >= 50.0),
                      key=lambda n: (n not in pokemon, -lift(n), n))
        odd = [n for n in seen_p if n not in mine or mine[n]["incl"] < 10.0]
        fit_text = ", ".join(f"{n} ({mine[n]['incl']:.0f}% of lists, usually {mine[n]['avg']:.0f})"
                             for n in fits[:max_fit]) or "none"
        line = f"{i}. {r['deck']} {prob * 100:.0f}% (played by {popularity(r):.1f}% of the field) - fits: {fit_text}"
        if odd:
            line += "; odd for it: " + ", ".join(
                f"{n} ({mine[n]['incl']:.0f}%)" if n in mine else f"{n} (not played)" for n in odd[:max_odd])
        lines.append(line)
    return "\n".join(lines)


# ── Your own decklist from the cards you showed (auto-capture) ────────────
DECK_SIZE = 60
BASIC_ENERGY = frozenset(f"{t} Energy" for t in
                         ("Grass", "Fire", "Water", "Lightning", "Psychic", "Fighting", "Darkness", "Metal"))
# Standard-era ACE SPECs (a deck plays at most one, one copy). Names as card_name() spells them.
ACE_SPECS = frozenset({
    "Amulet of Hope", "Awakening Drum", "Brilliant Blender", "Dangerous Laser", "Deluxe Bomb",
    "Energy Search Pro", "Enriching Energy", "Grand Tree", "Gravity Gemstone", "Hero's Cape",
    "Hyper Aroma", "Legacy Energy", "Master Ball", "Max Rod", "Maximum Belt", "Megaton Blower",
    "Miracle Headset", "Neo Upper Energy", "Neutralization Zone", "Poké Vital A", "Precious Trolley",
    "Prime Catcher", "Reboot Pod", "Scoop Up Cyclone", "Scramble Switch", "Secret Box",
    "Sparkling Crystal", "Survival Brace", "Treasure Tracker", "Unfair Stamp",
})


def legal_copies(name, seen):
    """Copies of `name` a legal deck can hold, given `seen` in one game:
    any number of basic Energy, 1 of an ACE SPEC, else at most 4. More seen
    than that means a card was recovered and played again."""
    if name in BASIC_ENERGY:
        return seen
    return min(seen, 1 if name in ACE_SPECS else MAX_COPIES)


CONFIRM_GAMES = 3  # games after the 60th card that must show nothing new


def merge_seen(games, size=DECK_SIZE, confirm=CONFIRM_GAMES):
    """Your deck from the cards you showed over several games of it.

    games: [{card: copies seen}] newest game first (log_deck_counts). Each
    card counts its max copies in any one game (capped to the legal number).
    Games are added newest first while the union still fits a legal deck (at
    most `size` cards, one ACE SPEC); the first game that doesn't (deck
    edited, or a card over-counted) ends it.

    Adding games one by one, the union tends to land on exactly `size` just
    before it overflows, even when an older version's tech fills the place
    of a copy never seen. So the list is only complete once `confirm` more
    games fit it without adding anything.

    Returns {"cards": {card: copies}, "total", "games": games used,
    "confirmed": games after the union reached `size`, "complete",
    "stop": None or why the next game was left out}."""
    cards, used, stop, confirmed = {}, 0, None, 0
    for game in games:
        merged = dict(cards)
        for name, n in (game or {}).items():
            merged[name] = max(merged.get(name, 0), legal_copies(name, max(1, int(n))))
        aces = sorted(n for n in merged if n in ACE_SPECS)
        if len(aces) > 1:
            stop = "two ACE SPECs: " + ", ".join(aces)
        elif sum(merged.values()) > size:
            stop = f"{sum(merged.values())} cards > {size}"
        if stop:
            break
        if sum(cards.values()) == size:
            confirmed += 1  # already full and still fits: nothing new
        cards, used = merged, used + 1
    total = sum(cards.values())
    return {"cards": cards, "total": total, "games": used, "confirmed": confirmed,
            "complete": total == size and confirmed >= confirm, "stop": stop}


def card_prints(rows=(), lists=()):
    """{card: (cat, set, number)} for writing a list: prints from your own
    PTCGL exports first, then the meta sheet's most played print."""
    prints = {}
    for text in lists:
        cat = "P"
        for line in (text or "").splitlines():
            line = line.strip()
            # "Pok.?mon": older stored exports have a mangled é
            head = re.match(r"(Pok.?mon|Trainer|Energy)\s*:\s*\d+$", line, re.IGNORECASE)
            if head:
                cat = "P" if head.group(1).lower().startswith("pok") else CATS[head.group(1).lower()]
                continue
            m = re.match(r"\d+\s+(.+?)\s+([A-Za-z0-9-]{2,6})\s+([A-Za-z0-9-]+)$", line)
            if m:
                prints.setdefault(card_name(m.group(1)), (cat, m.group(2), m.group(3)))
    for row in rows:
        for c in sorted(row.get("cards") or [], key=lambda c: -(c.get("incl") or 0)):
            if c.get("set") and c.get("number"):
                prints.setdefault(c["name"], (c["cat"], c["set"], str(c["number"])))
    return prints


def format_list(cards, prints):
    """(PTCGL export text for {card: copies}, []) or (None, [cards with no
    known print]). Basic Energy is written as PTCGL does ("Basic {D} Energy")."""
    missing = sorted(n for n in cards if n not in prints)
    if missing:
        return None, missing
    symbol = {v: k for k, v in ENERGY_TYPES.items()}
    out = []
    for cat in ("P", "T", "E"):
        names = sorted((n for n in cards if prints[n][0] == cat), key=lambda n: (-cards[n], n))
        out.append(f"{CAT_NAMES[cat]}: {sum(cards[n] for n in names)}")
        for n in names:
            shown = f"Basic {{{symbol[n.split()[0]]}}} Energy" if n in BASIC_ENERGY else n
            out.append(f"{cards[n]} {shown} {prints[n][1]} {prints[n][2]}")
        out.append("")
    out.append(f"Total Cards: {sum(cards.values())}")
    return "\n".join(out), []


# Trainers whose "shuffled ... into their deck" puts cards from the discard
# pile back (not from the hand, like Lillie's Determination or Unfair Stamp).
RECOVERY_TRAINERS = frozenset({"Energy Recycler", "Super Rod", "Pal Pad", "Energy Retrieval", "Night Stretcher"})


def log_deck_counts(battlelog, player, other=None):
    """{card: copies} that `player`'s deck must hold, from one battle log:
    the most copies of each card out of the hand and deck at the same time
    (in play or in the discard pile). Unlike log_card_counts, a card that
    goes back and is played again doesn't count twice: Night Stretcher
    ("moved X to their hand"), an ability that shuffles the Pokemon back
    ("played Dudunsparce." / "X used Run Away Draw", then "shuffled 2 cards
    into their deck" with the cards listed) and Energy Recycler lower the
    count; "played Prism Tower." on a Stadium already in play is its effect,
    not a card. Cards only shown (mulligan, search) count 1. Not capped: see
    legal_copies."""
    if not battlelog or not player:
        return {}
    names = log_card_counts(battlelog, player, other, cap=None)
    out, peak, pokemon, stadiums, used = {}, {}, set(), set(), set()
    pending = False   # the current action returns cards from play / discard to the deck
    bullets = None    # what the "•" list under the last line is: "put" / "return"

    def ok(name):  # a card name, not "a card" / "2 cards"
        return name and name[0].isupper() and ":" not in name and not re.search(r"\d", name)

    def put(name):
        if ok(name):
            out[name] = out.get(name, 0) + 1
            peak[name] = max(peak.get(name, 0), out[name])

    def back(name):
        if out.get(name, 0) > 0:
            out[name] -= 1

    for raw in battlelog.splitlines():
        line = raw.strip().replace("’", "'")
        if not line:
            continue
        if line.startswith("•"):
            for item in line.lstrip("• ").split(","):
                if bullets == "put":
                    pokemon.add(card_name(item))
                    put(card_name(item))
                elif bullets == "return":
                    back(card_name(item))
            continue
        bullets = None
        sub = line.startswith("- ")
        body = line[2:] if sub else line
        in_play = re.search(r" played (.+?) to the Stadium spot", body)
        if in_play:
            stadiums.add(card_name(in_play.group(1)))  # either player's
        if not body.startswith(player):
            if not sub:
                pending = False
            continue
        text = body[len(player):]
        if other and other in text:
            text = text[:text.index(other)]
        if text.startswith("'s "):
            # "<player>'s Dudunsparce used Run Away Draw." (also attacks; harmless)
            if not sub:
                pending = bool(re.match(r"'s .+? used ", text))
            continue
        if not sub:
            pending = False
        evolved = re.match(r"\s+evolved (.+?) to (.+?)(?: in the | on the |\.?$)", text)
        benched = re.match(r"\s+played (.+?) to the (?:Bench|Active Spot)", text)
        stadium = re.match(r"\s+played (.+?) to the Stadium spot", text)
        played = re.match(r"\s+played (.+?)\.?$", text)
        attached = re.match(r"\s+attached (.+?)(?: to | in the |\.?$)", text)
        moved = re.match(r"\s+moved " + re.escape(player) + r"'s (.+?) to their hand", text)
        shuffled = re.match(r"\s+shuffled (.+?) into their deck", text)
        if "played them to the Bench" in text:
            bullets = "put"
        elif evolved:
            pokemon.update(card_name(evolved.group(n)) for n in (1, 2))
            put(card_name(evolved.group(2)))
        elif benched:
            pokemon.add(card_name(benched.group(1)))
            put(card_name(benched.group(1)))
        elif stadium:
            put(card_name(stadium.group(1)))
        elif played:
            name = card_name(played.group(1))
            if name in pokemon:
                pending = True  # an ability ("played Dudunsparce."), not a card
            elif name in stadiums:
                used.add(name)  # the Stadium's effect ("played Prism Tower."), maybe the opponent's
            else:
                put(name)
                pending = name in RECOVERY_TRAINERS
        elif attached:
            put(card_name(attached.group(1)))
        elif moved:
            back(card_name(moved.group(1)))
        elif shuffled and pending:
            what = shuffled.group(1)
            if re.fullmatch(r"\d+ cards?", what):
                bullets = "return"
            elif what != "their deck":
                back(card_name(what))
    return {n: max(1, peak.get(n, 0)) for n in set(names) | set(peak)
            if ok(n) and not (n in used and not peak.get(n))}
