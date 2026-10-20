"""
How much of each game goes to which opponent archetype, for the statistics.

A stored opponent label is right far less often than its confidence says:
labels stored at 90-94% agree with the opponent's revealed cards only about
half the time (DevVault "Stats Review 2026-10-20"). Counting every label as
certain makes matchup cells, META FACED and the Score's opponent cells look
surer than they are. So unless you set the deck yourself, a game is split:
LABEL_WEIGHT to the stored label, the rest over the card matcher's ranking
(card_usage.classify: an independent second opinion), tempered because those
probabilities are overconfident too. Agreeing sources give the label ~0.9-1.0
of the game; a disagreeing card read takes up to half of it.

The card ranking is stored per battle by the parser (battles.card_ranked).
Older battles get it once from their log file, cached by log hash in
.label_cards_cache.json (stale when the meta sheet changes).
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, ".label_cards_cache.json")

LABEL_WEIGHT = 0.5        # until calibrated on manually confirmed labels (Stats TODO L10)
CARD_TEMPERATURE = 2.0    # p^(1/T): 78/93 card top picks are >= 85% but only 57% agree
CERTAIN_SOURCES = {"Manual", "Import"}


def temper(ranked, t=CARD_TEMPERATURE):
    """[(deck, p)] -> the same decks with p^(1/t), renormalised."""
    powered = [(d, max(0.0, float(p)) ** (1.0 / t)) for d, p in ranked or [] if d]
    total = sum(p for _d, p in powered)
    return [(d, p / total) for d, p in powered] if total > 0 else []


def distribution(label, source, card_ranked):
    """[(deck name, share of the game)], shares summing to 1."""
    label = label or ""
    cards = temper(card_ranked)
    if (source or "") in CERTAIN_SOURCES or not cards:
        return [(label, 1.0)]
    shares = {label: LABEL_WEIGHT}
    for deck, p in cards:
        shares[deck] = shares.get(deck, 0.0) + (1.0 - LABEL_WEIGHT) * p
    return list(shares.items())


# ── backfill for battles stored before card_ranked existed ─────────────
def _load_cache(stamp):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and data.get("stamp") == stamp:
            return data.get("ranked") or {}
    except Exception:
        pass
    return {}


def _save_cache(stamp, ranked):
    tmp = CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({"stamp": stamp, "ranked": ranked}, handle)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


def fill_card_ranked(battles, meta_rows, stamp=""):
    """Give every battle without a stored card ranking one from its log
    (in place). meta_rows need card data; stamp identifies the sheet."""
    missing = [b for b in battles if b.get("card_ranked") is None and b.get("log_hash")
               and (b.get("source") or "") not in CERTAIN_SOURCES]
    if not missing or not any(r.get("cards") for r in meta_rows or []):
        return battles
    cache = _load_cache(stamp)
    dirty = False
    extract = None
    for b in missing:
        key = b["log_hash"]
        if key not in cache:
            if extract is None:
                extract = _extractor(meta_rows)
            cache[key] = extract(b.get("log_file"))
            dirty = True
        b["card_ranked"] = [tuple(x) for x in cache[key]] if cache[key] else []
    if dirty:
        _save_cache(stamp, cache)
    return battles


def _extractor(meta_rows):
    import card_usage
    from AIParseBattleLog import read_battlelog_file, parse_opponent_from_log
    from app_settings import load_username
    username = load_username() or ""
    card_usage.set_known_cards(c["name"] for r in meta_rows for c in r.get("cards") or [])

    def extract(log_file):
        if not log_file:
            return []
        path = log_file if os.path.isabs(log_file) else os.path.join(BASE_DIR, "Logs", log_file)
        log = read_battlelog_file(path) if os.path.exists(path) else None
        if not log:
            return []
        try:
            opponent = parse_opponent_from_log(log, username)
            copies = card_usage.log_card_counts(log, opponent, username)
            return [[r["deck"], round(float(p), 4)] for r, p in card_usage.classify(copies, meta_rows)]
        except Exception:
            return []
    return extract
