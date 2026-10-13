"""Tests for card usage and the meta-source helpers (run: python -m pytest test_card_usage.py, or python test_card_usage.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import card_usage as C
import meta_sources as M

EXPORT = """Pokémon: 4
3 Gastly POR 48
1 Gastly POR 48
2 Gengar ex 30C 90

Trainer: 2
4 Ultra Ball MEG 131
2 Night Stretcher SSP 251

Energy: 2
6 Basic {D} Energy MEE 7
4 Shadowy {D} Energy PBL 83

Total Cards: 22
"""


def test_energy_names_match_limitless():
    assert C.card_name("Basic {D} Energy") == "Darkness Energy"
    assert C.card_name("Basic {P} Energy") == "Psychic Energy"
    assert C.card_name("Shadowy {D} Energy") == "Shadowy Darkness Energy"
    assert C.card_name("  Ultra   Ball ") == "Ultra Ball"


def test_parse_merges_prints_and_sections():
    cards = C.parse_list(EXPORT)
    assert cards[("P", "Gastly")] == 4
    assert cards[("T", "Ultra Ball")] == 4
    assert cards[("E", "Darkness Energy")] == 6
    assert sum(cards.values()) == 22


def test_compare_marks_missing_core_and_own_cards():
    meta = [{"name": "Gastly", "cat": "P", "set": "POR", "number": "48", "incl": 100.0, "avg": 3.9, "per_list": 3.9},
            {"name": "Rare Candy", "cat": "T", "set": "MEG", "number": "125", "incl": 95.0, "avg": 3.0, "per_list": 2.85},
            {"name": "Ultra Ball", "cat": "T", "set": "MEG", "number": "131", "incl": 40.0, "avg": 2.0, "per_list": 0.8}]
    rows = C.compare(meta, C.parse_list(EXPORT))
    by = {r["name"]: r for r in rows}
    assert by["Gastly"]["typical"] == 4 and by["Gastly"]["diff"] == 0
    assert by["Rare Candy"]["mine"] == 0 and by["Rare Candy"]["role"] == "core"
    assert by["Ultra Ball"]["typical"] == 0 and by["Ultra Ball"]["role"] == "tech"  # under half the lists
    assert by["Gengar ex"]["role"] == "only yours"
    assert [c["name"] for c in C.summary(rows)["missing_core"]] == ["Rare Candy"]
    assert C.compare(meta)[0]["mine"] is None  # no list chosen


def test_best_archetype_needs_a_real_match():
    mine = C.parse_list(EXPORT)
    near = {"id": "a", "cards": [{"name": "Gastly", "cat": "P", "per_list": 4.0},
                                 {"name": "Ultra Ball", "cat": "T", "per_list": 4.0},
                                 {"name": "Darkness Energy", "cat": "E", "per_list": 8.0},
                                 {"name": "Gengar ex", "cat": "P", "per_list": 3.0},
                                 {"name": "Shadowy Darkness Energy", "cat": "E", "per_list": 4.0}]}
    far = {"id": "b", "cards": [{"name": "Dreepy", "cat": "P", "per_list": 4.0}]}
    assert C.best_archetype([far, near], mine, minimum=0.2)["id"] == "a"
    assert C.best_archetype([far], mine) is None


def test_summarize_lists_counts_lists_not_prints():
    lists = [("Gengar", [("P", "Gastly", "POR", "48", 3), ("P", "Gastly", "SVI", "1", 1), ("T", "Ultra Ball", "MEG", "131", 4)]),
             ("Gengar", [("P", "Gastly", "POR", "48", 4)]),
             ("Dragapult", [])]
    out = M._summarize_lists(lists)
    assert out["Gengar"]["n"] == 2 and "Dragapult" not in out
    assert out["Gengar"]["c"]["P|Gastly"][:2] == [2, 8]  # in 2 lists, 8 copies in all
    assert out["Gengar"]["c"]["T|Ultra Ball"][:2] == [1, 4]


def test_throttle_reads_rate_limit_header():
    class Resp:
        def __init__(self, status, headers):
            self.status_code, self.headers = status, headers
    t = M._ApiThrottle()
    t.after(Resp(200, {"RateLimit": '"50-in-5min"; r=0; t=120'}))
    assert t.remaining == 0 and t.reset_at > 0
    t.deadline = 0.0  # any wait would pass the deadline
    try:
        t.before()
        assert False, "should have raised"
    except M.RateLimited:
        pass
    t2 = M._ApiThrottle()
    t2.after(Resp(200, {"RateLimit": '"50-in-5min"; r=12; t=40'}))
    t2.before()  # quota left: no wait, no error
    assert t2.remaining == 12


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as exc:
                failed += 1
                print("FAIL", name, exc)
    sys.exit(1 if failed else 0)
