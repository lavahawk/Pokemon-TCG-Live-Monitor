"""Tests for the local battle-log parsing in AIParseBattleLog (run: python test_parser.py).

Importing AIParseBattleLog opens a BattleDatabase, so the default DB path is
redirected to a temp file first; the user's files (.last_deck, the meta
cache, settings) are redirected or stubbed too. No network: OpenAI is a fake
module and meta_sources._api_get raises.
"""
import atexit
import json
import os
import shutil
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TMP = tempfile.mkdtemp(prefix="ptcgl_test_parser_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

import BattleDatabase as BDB

TEST_DB = os.path.join(TMP, "parser.db")
BDB.DB_PATH = TEST_DB
BDB.BattleDatabase.__init__.__defaults__ = (TEST_DB, False)  # db = BattleDatabase() at import time

import meta_sources


def _no_network(*_a, **_k):
    raise AssertionError("network access in a test")


meta_sources._api_get = _no_network

import AIParseBattleLog as P
import card_usage

assert os.path.abspath(P.db.db_path) == os.path.abspath(TEST_DB), "parser must not open the real DB"

ME, OPP = "22lava44", "Ntmygamegenre"
META_FILE = os.path.join(TMP, "meta_cache.json")
P.LAST_DECK_FILE = os.path.join(TMP, ".last_deck")          # absent: no OCR deck
P.LAST_RANK_FILE = os.path.join(TMP, ".last_rank")
P.LIMITLESS_STANDARD_CACHE_FILE = META_FILE                 # absent unless a test writes it
P.TOURNAMENT_FLAG_FILE = os.path.join(TMP, ".in_tournament")
P.CHAT_CAPTURE_FILE = os.path.join(TMP, ".chat_capture.json")
P.EXCEL_FILE = os.path.join(TMP, "none.xlsx")
P.load_username = lambda: ME
P._console_available = lambda: False
P.is_local_only_mode = lambda: True
P.load_api_key = lambda: None


def _find_test_battle():
    """TestBattle.txt is gitignored (real usernames): look next to this file,
    then in the main checkout when running from .claude/worktrees/<name>/."""
    for path in (os.path.join(HERE, "TestBattle.txt"),
                 os.path.normpath(os.path.join(HERE, "..", "..", "..", "TestBattle.txt"))):
        if os.path.exists(path):
            return path
    return None


TEST_BATTLE = _find_test_battle()
BATTLE = P.read_battlelog_file(TEST_BATTLE) if TEST_BATTLE else None


class Skip(Exception):
    pass


def need_battle():
    if not BATTLE:
        raise Skip("TestBattle.txt not found")


def _no_meta():
    if os.path.exists(META_FILE):
        os.remove(META_FILE)


def _write_meta(rows):
    with open(META_FILE, "w", encoding="utf-8") as handle:
        json.dump({"rows": rows}, handle)


def _row(deck, share, cards, lists=50):
    return {"deck": deck, "share_en": share, "lists": lists, "count": lists,
            "cards": [{"name": n, "cat": cat, "incl": incl, "avg": avg} for n, cat, incl, avg in cards]}


META_ROWS = [
    _row("Dragapult ex", 20, [("Dreepy", "P", 100, 4), ("Drakloak", "P", 100, 4), ("Dragapult ex", "P", 100, 3),
                              ("Munkidori", "P", 60, 1), ("Pecharunt", "P", 50, 1), ("Poké Pad", "T", 70, 3)]),
    _row("Blaziken ex", 10, [("Torchic", "P", 100, 4), ("Combusken", "P", 100, 2), ("Blaziken ex", "P", 100, 3)]),
    _row("Gengar ex", 10, [("Gastly", "P", 100, 4), ("Haunter", "P", 90, 2), ("Gengar ex", "P", 100, 3)]),
]


# ── TestBattle.txt (real log) ──────────────────────────────────────────────
def test_real_log_reads_crlf_and_names():
    need_battle()
    assert "\r" not in BATTLE  # CRLF file read in text mode: newlines normalised
    assert BATTLE.splitlines()[0] == "Setup"
    assert P.parse_opponent_from_log(BATTLE, ME) == OPP
    assert P.parse_opponent_from_log(BATTLE, OPP) == ME
    assert P.parse_opponent_from_log(BATTLE, "  22LAVA44 ") == OPP  # case / whitespace-insensitive
    assert P.parse_opponent_from_log(BATTLE, "") is None


def test_real_log_result():
    need_battle()
    # "Opponent Knocked Out all your Pokémon ... Prize cards. Ntmygamegenre wins." isn't a known prefix
    assert P.parse_winner_from_log(BATTLE) == OPP
    assert P.parse_result_from_log(BATTLE, ME) == "Loss"
    assert P.parse_result_from_log(BATTLE, OPP) == "Win"
    assert P.parse_result_from_log(BATTLE, None) is None


def test_real_log_turn_headers():
    need_battle()
    # The parser keeps no turn counter / first-player field; the turn headers
    # are what parse_opponent_from_log relies on. The opponent went first.
    headers = [l for l in BATTLE.splitlines() if l.endswith("'s Turn")]
    assert headers[0] == f"{OPP}'s Turn" and headers[1] == f"{ME}'s Turn"
    assert len(headers) == 17
    assert f"{OPP} decided to go first." in BATTLE


def test_real_log_opponent_cards():
    need_battle()
    card_usage.set_known_cards(c["name"] for r in META_ROWS for c in r["cards"])
    counts = card_usage.log_card_counts(BATTLE, OPP, ME)
    for card in ("Torchic", "Dreepy", "Drakloak", "Dragapult ex", "Pecharunt", "Munkidori", "Shaymin",
                 "Poké Pad", "Ultra Ball", "Rare Candy", "Lillie's Clefairy ex", "Fire Energy"):
        assert card in counts, card
    for mine in ("Cinderace", "Mega Zygarde ex", "Fighting Gong", "Fighting Energy"):
        assert mine not in counts, mine
    assert counts["Poké Pad"] == 3 and counts["Drakloak"] == 3 and counts["Dragapult ex"] == 2
    assert all(1 <= n <= card_usage.MAX_COPIES for n in counts.values())
    assert not any(":" in c or any(ch.isdigit() for ch in c) for c in counts)


def test_real_log_local_parse_without_meta():
    need_battle()
    _no_meta()
    out = P.local_fallback_parse(BATTLE, ME)
    # No card data: the opponent's first Active Pokemon is the guess.
    assert out["OpponentsDeck"] == "Torchic"
    assert out["deck_source"] == "guess"
    assert out["Confidence"] == 35
    assert out["Win_or_Loss"] == "Loss"
    assert out["My_deck"] == "Unknown Deck"
    assert out["Candidates"] == [("Torchic", 0.35)]


def test_real_log_local_parse_with_card_evidence():
    need_battle()
    _write_meta(META_ROWS)
    try:
        ev = P.card_evidence(BATTLE, ME)
        assert ev["ranked"][0][0] == "Dragapult ex" and ev["ranked"][0][1] > 0.9
        assert {"Dreepy", "Drakloak", "Dragapult ex", "Torchic"} <= ev["pokemon"]
        assert "Cinderace" not in ev["cards"]
        out = P.local_fallback_parse(BATTLE, ME)
        assert out["OpponentsDeck"] == "Dragapult ex"
        assert out["deck_source"] == "cards"  # >= 85% and "dragapult" was seen
        assert out["Confidence"] == int(round(ev["ranked"][0][1] * 100))
        cands = out["Candidates"]
        assert 1 <= len(cands) <= 3 and cands[0] == ("Dragapult ex", out["Confidence"] / 100.0)
        assert len({c[0].casefold() for c in cands}) == len(cands)
        assert [c[0] for c in cands] == [d for d, _p in ev["ranked"]][:len(cands)]
        assert sum(p for _d, p in cands) <= 1.0 + 0.005  # the pick's probability is the rounded confidence
    finally:
        _no_meta()


# ── small synthetic logs ───────────────────────────────────────────────────
def _log(*lines):
    return "\r\n".join(lines)


def test_names_with_dots_spaces_and_accents():
    log = _log("Setup", "Dr. Oak chose heads for the opening coin flip.", "Dr. Oak won the coin toss.",
               "Dr. Oak decided to go second.", "", "Turn # 1 - Zoé B's Turn", "Zoé B drew a card.",
               "", "Turn # 2 - Dr. Oak's Turn", "Dr. Oak drew a card.",
               "Opponent took all of their Prize cards. Zoé B wins.")
    assert P.parse_opponent_from_log(log, "Dr. Oak") == "Zoé B"
    assert P.parse_opponent_from_log(log, "zoé b") == "Dr. Oak"
    assert P.parse_winner_from_log(log) == "Zoé B"
    assert P.parse_result_from_log(log, "Dr. Oak") == "Loss"
    assert P.parse_result_from_log(log, "ZOÉ B") == "Win"


def test_result_prefixes_and_unknown_sentence():
    for prefix in P.RESULT_PREFIXES:
        assert P.parse_winner_from_log(f"x\n{prefix} Bob wins.") == "Bob", prefix
    assert P.parse_winner_from_log("x\nSomething new happened. Bob wins.\n\n") == "Bob"
    assert P.parse_winner_from_log("Bob's Turn\nBob drew a card.") is None  # no result line
    assert P.parse_winner_from_log("") is None and P.parse_winner_from_log(None) is None
    # the last "wins." line counts
    assert P.parse_winner_from_log("Opponent conceded. Al wins.\nYou conceded. Bo wins.") == "Bo"
    # the user's own name (with a dot) is returned exactly
    assert P.parse_winner_from_log("All Prize cards taken. j.doe wins.", "J.Doe") == "J.Doe"


def test_local_parse_without_result_or_opponent():
    _no_meta()
    out = P.local_fallback_parse("Setup\n22lava44 drew 7 cards for the opening hand.", ME)
    assert out["OpponentsDeck"] == "Unknown (local mode)"
    assert out["Confidence"] == 0 and out["deck_source"] == "none" and out["Candidates"] == []
    assert out["Win_or_Loss"] == "Loss"  # no "wins." line and no console: stored as a loss


def test_local_parse_uses_ocr_deck():
    _no_meta()
    with open(P.LAST_DECK_FILE, "w", encoding="utf-8") as handle:
        handle.write("  Gardevoir ex \n")
    try:
        log = _log("Setup", "bob played Ralts to the Active Spot.", "opp played Gastly to the Active Spot.",
                   "", "opp's Turn", "", "bob's Turn", "All Prize cards taken. bob wins.")
        P.load_username = lambda: "bob"
        out = P.local_fallback_parse(log, "bob")
        assert out["My_deck"] == "Gardevoir ex"
        assert out["OpponentsDeck"] == "Gastly" and out["Win_or_Loss"] == "Win"
    finally:
        P.load_username = lambda: ME
        os.remove(P.LAST_DECK_FILE)


def test_infer_strips_rule_box_suffix():
    log = _log("me played Pikachu to the Active Spot.", "opp played Dreepy ex to the Active Spot.",
               "opp's Turn", "me's Turn")
    P.load_username = lambda: "me"
    try:
        assert P.infer_opponent_deck_from_log(log) == "Dreepy"
    finally:
        P.load_username = lambda: ME
    assert P.infer_opponent_deck_from_log("") is None


def test_tournament_flag_needs_matching_opponent():
    log = _log("me's Turn", "Rival X's Turn")
    assert P.is_tournament_battle(log, "me") is False  # no flag file
    with open(P.TOURNAMENT_FLAG_FILE, "w", encoding="utf-8") as handle:
        json.dump({"in_tournament": True, "opponent": "rival x"}, handle)
    try:
        assert P.is_tournament_battle(log, "me") is True
        assert P.is_tournament_battle(_log("me's Turn", "Someone's Turn"), "me") is False
        old = os.path.getmtime(P.TOURNAMENT_FLAG_FILE) - P.TOURNAMENT_FLAG_MAX_AGE_S - 60
        os.utime(P.TOURNAMENT_FLAG_FILE, (old, old))
        assert P.is_tournament_battle(log, "me") is False  # stale flag ignored
    finally:
        os.remove(P.TOURNAMENT_FLAG_FILE)


# ── candidates / confidence helpers ────────────────────────────────────────
def test_merge_candidates_dedupes_and_fills_probabilities():
    ranked = [("Dragapult ex", 0.7), ("Gengar ex", 0.2), ("Blaziken ex", 0.1)]
    out = P.merge_candidates("dragapult  EX", None, [("Unknown deck", 0.5), ("Gengar ex", None)], ranked)
    assert out == [("dragapult EX", 0.7), ("Gengar ex", 0.2), ("Blaziken ex", 0.1)]
    assert P.merge_candidates(None, None, [], ranked, limit=2) == ranked[:2]
    assert P.merge_candidates("", None, [], []) == []
    assert P.merge_candidates("New Deck", 0.4, [], ranked)[0] == ("New Deck", 0.4)


def test_deck_confidence_blends_ai_and_cards():
    assert P.deck_confidence(80, "Anything", []) == 80
    assert P.deck_confidence(80, "Dragapult ex", [("Dragapult ex", 0.9)]) == 85
    assert P.deck_confidence(80, " dragapult   ex ", [("Dragapult ex", 0.9)]) == 85
    assert P.deck_confidence(90, "Charizard ex", [("Dragapult ex", 0.9)]) == 45  # cards don't support it


def test_confidence_and_candidate_coercion():
    c = P._coerce_confidence_value
    assert c(87) == 87 and c("87%") == 87 and c("0.5") == 0 and c(150) == 100 and c(-5) == 0
    assert c({"value": "72"}) == 72 and c(["", 64]) == 64 and c(None) == 0 and c("high", default=40) == 40
    assert c(True) == 100 and c(87.6) == 88
    cands = P._coerce_candidates({"Candidates": [{"deck": " Gengar  ex", "probability": 60},
                                                 {"name": "Dragapult", "confidence": "30%"},
                                                 "Raging Bolt", {"deck": ""}]})
    assert cands == [("Gengar ex", 0.6), ("Dragapult", 0.3), ("Raging Bolt", None)]
    assert P._coerce_candidates({"candidates": {"A": 50}}) == [("A", 0.5)]
    assert P._coerce_candidates({}) == [] and P._coerce_candidates({"Candidates": "x"}) == []


# ── ai_parse with a fake OpenAI client (no network) ────────────────────────
def _fake_openai(payload, fail_models=()):
    calls = []

    class _Completions:
        def create(self, model, messages, response_format):
            calls.append(model)
            if model in fail_models:
                raise RuntimeError("model gone")
            msg = types.SimpleNamespace(content=json.dumps(payload))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class OpenAI:
        def __init__(self, **_kw):
            self.chat = types.SimpleNamespace(completions=_Completions())

    module = types.ModuleType("openai")
    module.OpenAI = OpenAI
    return module, calls


def _with_openai(module, fn):
    saved = sys.modules.get("openai")
    sys.modules["openai"] = module
    try:
        return fn()
    finally:
        if saved is None:
            sys.modules.pop("openai", None)
        else:
            sys.modules["openai"] = saved


def test_ai_parse_candidates_and_fallback_model():
    _no_meta()
    payload = {"My_deck": "Zygarde", "OpponentsDeck": "Dragapult ex", "Win_or_Loss": "loss",
               "Confidence": "70%", "Candidates": [{"deck": "Dragapult ex", "probability": 70},
                                                   {"deck": "Gengar ex", "probability": 20},
                                                   {"deck": "Raging Bolt", "probability": 5},
                                                   {"deck": "Extra", "probability": 5}]}
    module, calls = _fake_openai(payload, fail_models=(P.AI_MODELS[0],))
    out = _with_openai(module, lambda: P.ai_parse("me's Turn\nopp's Turn", "me", "sk-test"))
    assert calls == P.AI_MODELS[:2]  # first model failed, second used
    assert out["OpponentsDeck"] == "Dragapult ex" and out["Win_or_Loss"] == "Loss"
    assert out["Confidence"] == 70 and out["deck_source"] == "ai"
    assert out["Candidates"] == [("Dragapult ex", 0.7), ("Gengar ex", 0.2), ("Raging Bolt", 0.05)]


def test_ai_parse_overruled_by_clear_card_evidence():
    need_battle()
    _write_meta(META_ROWS)
    try:
        payload = {"My_deck": "x", "OpponentsDeck": "Gengar ex", "Win_or_Loss": "Win", "Confidence": 90}
        module, _calls = _fake_openai(payload)
        out = _with_openai(module, lambda: P.ai_parse(BATTLE, ME, "sk-test"))
        assert out["OpponentsDeck"] == "Dragapult ex" and out["deck_source"] == "cards"
        assert out["Candidates"][0][0] == "Dragapult ex"
        assert 85 <= out["Confidence"] <= 100
    finally:
        _no_meta()


def test_ai_parse_raises_when_every_model_fails():
    module, calls = _fake_openai({}, fail_models=tuple(P.AI_MODELS))
    try:
        _with_openai(module, lambda: P.ai_parse("x", "me", "sk-test"))
        assert False, "should have raised"
    except RuntimeError:
        pass
    assert calls == P.AI_MODELS


def test_regression_winner_needs_whole_name():
    assert P.parse_winner_from_log("Opponent took all of their Prize cards. MrAsh wins.", "Ash") == "MrAsh"
    assert P.parse_result_from_log("Opponent took all of their Prize cards. Mr. Ash wins.", "Ash") == "Loss"
    assert P.parse_result_from_log("All Prize cards taken. Ash wins.", "Ash") == "Win"


def test_regression_numbered_header_is_not_a_name():
    log = _log("Turn # 1 - Zoé B's Turn", "Zoé B drew a card.")
    assert P.log_player_names(log) == ["Zoé B"]


def test_regression_opponent_deck_line_anchored_and_accents():
    saved = P.load_username
    try:
        P.load_username = lambda: "TrashAsh"
        log = _log("Ash decided to go first.", "TrashAsh played Pikachu to the Active Spot.",
                   "Ash played Flabébé to the Active Spot.")
        assert P.infer_opponent_deck_from_log(log) == "Flabébé"
    finally:
        P.load_username = saved


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Skip as exc:
                print(f"SKIP {name}: {exc}")
            except Exception as exc:
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failures else 0)
