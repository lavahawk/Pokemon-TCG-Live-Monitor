"""
Local opponent-deck predictor for manual mode: no AI, no network, no extra
packages, a few milliseconds per battle.

It re-ranks the card matcher (card_usage.classify: the opponent's revealed
cards vs public Limitless decklists) with what only your own games know:

  your ladder   how often you actually meet each deck (recent games count
                more) vs its tournament meta share. Ladder != tournaments.
  the opponent  someone you've played before most likely brought the same deck.
  your games    decks you've confirmed (not in the meta sheet, or rogue
                variants) are matched on the cards they showed you, so a
                deck the public lists don't know can still be suggested.

Leave-one-out on 60 AI-labelled games (2026-10-15): a tie with the matcher
alone (top-1 24/60, top-3 31/60). That data has nothing for it to learn: the
labels are AI picks that already follow the cards, no opponent was met twice
and nearly every deck is on the sheet. So everything is kept mild
(LADDER_MIX_MAX, rogue decks only win on their cards) and gains weight as
manually confirmed games pile up. Re-check with a leave-one-out run then.

Per-log card extraction is cached in .local_model_cache.json (by log hash),
so only new battles are read; labels come fresh from the DB, so a deck you
correct on the overlay card counts straight away.
"""

import json
import math
import os
import time
from collections import Counter, defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, ".local_model_cache.json")

HALF_LIFE_DAYS = 21.0   # ladder prior: a game 3 weeks ago counts half
LADDER_MIX_MAX = 0.25   # at most this much of the prior comes from your ladder...
LADDER_MIX_GAMES = 60.0  # ...reached after this many (recency-weighted) games
OPPONENT_BOOST = 4.0    # likelihood ratio for the deck an opponent used last time
FLOOR = 0.004           # P(card) for a deck never seen playing it
ROGUE_MIN_GAMES = 2     # a deck outside the meta sheet needs this many games to be suggested
SOURCE_WEIGHT = {"Manual": 1.5, "AI": 1.0, "Cards": 1.0, "OCR": 0.8, "Local": 0.5}
SKIP_LABELS = ("unknown", "other")


def _norm(name):
    return " ".join(str(name or "").split())


def _key(name):
    return _norm(name).casefold()


def _base(key):
    """"Dragapult ex" and "Dragapult" are one deck."""
    return " ".join(w for w in key.split() if w != "ex")


def _usable_label(name):
    key = _key(name)
    return bool(key) and not any(key.startswith(s) for s in SKIP_LABELS)


class LocalModel:
    """meta_rows: Limitless rows (deck, share, lists, cards[{name, incl, avg, cat}]).
    history: [{"deck", "copies": {card: n}, "opponent", "ts" (epoch s), "weight"}]."""

    def __init__(self, meta_rows=(), history=(), now=None):
        self.rows = [r for r in meta_rows or () if _usable_label(r.get("deck"))]
        self.now = now if now is not None else time.time()
        self.meta_keys = {_key(r["deck"]) for r in self.rows}
        self.names = {_key(r["deck"]): _norm(r["deck"]) for r in self.rows}
        alias = {_base(k): k for k in self.meta_keys}
        self.faced = Counter()
        self.games = defaultdict(list)  # deck key -> [copies, ...] (decks outside the sheet)
        self.opponents = defaultdict(Counter)
        for game in history or ():
            if not _usable_label(game.get("deck")):
                continue
            key = _key(game["deck"])
            key = alias.get(_base(key), key)  # your label's spelling -> the meta deck
            self.names.setdefault(key, _norm(game["deck"]))
            age_days = max(0.0, (self.now - float(game.get("ts") or self.now)) / 86400.0)
            self.faced[key] += float(game.get("weight", 1.0)) * 0.5 ** (age_days / HALF_LIFE_DAYS)
            if game.get("copies") and key not in self.meta_keys:
                self.games[key].append(game["copies"])
            opp = _key(game.get("opponent"))
            if opp:
                self.opponents[opp][key] += 1
        self.faced_total = sum(self.faced.values())

    # ── pieces ──
    def _meta_prior(self):
        import card_usage
        pops = {_key(r["deck"]): max(0.0, card_usage.popularity(r)) for r in self.rows}
        total = sum(pops.values()) or 1.0
        return {k: v / total for k, v in pops.items()}

    def _ladder_ratio(self, key, meta_p):
        """How much more (or less) often you meet this deck than the meta says."""
        if self.faced_total <= 0:
            return 1.0
        mix = LADDER_MIX_MAX * min(1.0, self.faced_total / LADDER_MIX_GAMES)
        n_decks = max(1, len(self.names))
        faced_p = (self.faced.get(key, 0.0) + 0.5) / (self.faced_total + 0.5 * n_decks)
        meta_p = max(meta_p, 1e-4)
        return ((1 - mix) * meta_p + mix * faced_p) / meta_p

    def _opponent_ratio(self, key, opponent):
        opp = self.opponents.get(_key(opponent)) if opponent else None
        if not opp or not opp.get(key):
            return 1.0
        return 1 + (OPPONENT_BOOST - 1) * opp[key] / sum(opp.values())

    def _mix(self):
        return LADDER_MIX_MAX * min(1.0, self.faced_total / LADDER_MIX_GAMES) if self.faced_total > 0 else 0.0

    def _rogue_share(self, copies, meta_prior):
        """Decks only your games know (not on the meta sheet). Scored with the
        meta decks on one naive-Bayes scale - prior x P(each seen card) - so a
        rogue deck only gets probability when its cards explain the game better.
        Returns ({rogue key: probability}, total rogue probability)."""
        seen = set(copies)
        rogues = {k: g for k, g in self.games.items() if len(g) >= ROGUE_MIN_GAMES}
        mix = self._mix()
        if not seen or not rogues or mix <= 0:
            return {}, 0.0
        n_decks = max(1, len(self.names))
        faced_p = lambda k: (self.faced.get(k, 0.0) + 0.5) / (self.faced_total + 0.5 * n_decks)
        relevant = {c for r in self.rows for c in (x["name"] for x in r.get("cards") or [])}
        relevant |= {c for games in rogues.values() for g in games for c in g}
        cards = seen & relevant
        scores = {}
        for row in self.rows:
            if not row.get("cards") or (row.get("lists") or 0) < 5:
                continue
            key = _key(row["deck"])
            incl = {c["name"]: c["incl"] / 100.0 for c in row["cards"]}
            prior = (1 - mix) * meta_prior.get(key, 0.0) + mix * faced_p(key)
            scores[key] = math.log(max(1e-6, prior)) + sum(
                math.log(max(FLOOR, min(0.999, incl.get(c, 0.0)))) for c in cards)
        rogue_scores = {}
        for key, games in rogues.items():
            n = len(games)
            rogue_scores[key] = math.log(max(1e-6, mix * faced_p(key))) + sum(
                math.log(max(FLOOR, min(0.999, (sum(1 for g in games if c in g) + 0.1) / (n + 1))))
                for c in cards)
        best = max(list(scores.values()) + list(rogue_scores.values()))
        total = sum(math.exp(v - best) for v in scores.values()) + sum(math.exp(v - best) for v in rogue_scores.values())
        probs = {k: math.exp(v - best) / total for k, v in rogue_scores.items()}
        return probs, sum(probs.values())

    # ── public ──
    def predict(self, copies=None, opponent=None, top=3):
        """[(deck name, probability)] best first. copies: {card: copies seen}."""
        import card_usage
        copies = dict(copies or {})
        meta_prior = self._meta_prior()
        ranked = card_usage.classify(copies, self.rows, top=len(self.rows)) if copies else []
        if ranked:
            base = {_key(r["deck"]): p for r, p in ranked}
        else:
            base = dict(meta_prior)  # nothing revealed (early concede): the prior alone
        weights = {}
        for key, p in base.items():
            if p > 0:
                weights[key] = p * self._ladder_ratio(key, meta_prior.get(key, 0.0)) * self._opponent_ratio(key, opponent)
        total = sum(weights.values())
        if total <= 0:
            return []
        rogue, rogue_total = self._rogue_share(copies, meta_prior)
        probs = {k: (1.0 - rogue_total) * w / total for k, w in weights.items()}
        for key, p in rogue.items():
            probs[key] = p * self._opponent_ratio(key, opponent)
        norm = sum(probs.values()) or 1.0
        order = sorted(probs, key=lambda k: -probs[k])[:top]
        return [(self.names.get(k, k), probs[k] / norm) for k in order]


# ── building from the app's data ─────────────────────────────────────────
def _load_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(cache):
    tmp = CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(cache, handle)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


def _timestamp(value):
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return None


def history_from_db(db, extract, exclude_hash=None):
    """Labelled battles as model history. extract(log_path) -> (opponent,
    {card: copies}) reads one log; results are cached by log hash."""
    conn = db._connect()
    try:
        rows = conn.execute("SELECT opponent_deck, deck_source, log_file, log_hash, timestamp "
                            "FROM battles WHERE log_file IS NOT NULL").fetchall()
    finally:
        conn.close()
    cache = _load_cache()
    dirty = False
    history = []
    for deck, source, log_file, log_hash, ts in rows:
        if not _usable_label(deck) or (exclude_hash and log_hash == exclude_hash):
            continue
        entry = cache.get(log_hash) if log_hash else None
        if entry is None:
            path = log_file if os.path.isabs(log_file) else os.path.join(BASE_DIR, "Logs", log_file)
            if not os.path.exists(path):
                continue
            try:
                opponent, copies = extract(path)
            except Exception:
                continue
            entry = {"opponent": opponent or "", "copies": dict(copies or {})}
            if log_hash:
                cache[log_hash] = entry
                dirty = True
        history.append({"deck": deck, "copies": entry["copies"], "opponent": entry["opponent"],
                        "ts": _timestamp(ts), "weight": SOURCE_WEIGHT.get(source or "", 1.0)})
    if dirty:
        _save_cache(cache)
    return history
