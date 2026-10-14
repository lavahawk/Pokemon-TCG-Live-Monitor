"""Tests for decklists.py (store, names, deck links) and card_usage edge cases
not covered by test_card_usage.py (run: python test_decklists.py).

decklists.STORE_FILE is redirected to a temp file; the user's .decklists.json
is never read or written.
"""
import atexit
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TMP = tempfile.mkdtemp(prefix="ptcgl_test_decklists_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

import card_usage as C
import decklists as D

D.STORE_FILE = os.path.join(TMP, ".decklists.json")


def reset_store():
    for path in (D.STORE_FILE, D.STORE_FILE + ".tmp"):
        if os.path.exists(path):
            os.remove(path)


DRAGAPULT = """Pokémon: 13
4 Dreepy TWM 128
4 Drakloak TWM 129
3 Dragapult ex TWM 130
2 Duskull SFA 18

Trainer: 37
4 Ultra Ball MEG 131
4 Rare Candy MEG 125
4 Buddy-Buddy Poffin TEF 144
25 Professor's Research SVI 189

Energy: 10
6 Basic {R} Energy MEE 2
4 Basic {P} Energy MEE 5

Total Cards: 60
"""

# same cards: other order, one card split over two prints of the same line
DRAGAPULT_SHUFFLED = """Pokémon: 13
2 Duskull SFA 18
3 Dragapult ex TWM 130
2 Dreepy TWM 128
2 Dreepy TWM 128
4 Drakloak TWM 129
Trainer: 37
25 Professor's Research SVI 189
4 Rare Candy MEG 125
4 Ultra Ball MEG 131
4 Buddy-Buddy Poffin TEF 144
Energy: 10
4 Basic {P} Energy MEE 5
6 Basic {R} Energy MEE 2
"""

GENGAR = """Pokemon: 12
4 Gastly POR 48
3 Haunter POR 49
3 Gengar ex 30C 90
2 Zoroark ex TWM 98

Trainer: 38
38 Ultra Ball MEG 131

Energy: 10
10 Basic {D} Energy MEE 7
"""


# ── recognising and naming exports ─────────────────────────────────────────

def _latest():
    lists = D.all_decklists()
    return lists[0] if lists else None

def test_is_ptcgl_decklist():
    assert D.is_ptcgl_decklist(DRAGAPULT) and D.is_ptcgl_decklist(GENGAR)
    assert D.is_ptcgl_decklist(DRAGAPULT.replace("\n", "\r\n"))  # CRLF clipboard
    assert not D.is_ptcgl_decklist("")
    assert not D.is_ptcgl_decklist(None)
    assert not D.is_ptcgl_decklist("Pokémon: 4\n4 Dreepy TWM 128\n")  # one section, too few lines
    small = "Pokémon: 5\n1 A AAA 1\n1 B AAA 2\n1 C AAA 3\nTrainer: 2\n1 D AAA 4\n1 E AAA 5\n"
    assert not D.is_ptcgl_decklist(small)  # 5 cards: not a deck
    assert not D.is_ptcgl_decklist(DRAGAPULT + "x" * 20000)  # huge clipboard
    assert D.card_count(DRAGAPULT) == 60 and D.card_count(None) == 0


def test_list_id_ignores_order_and_split_lines():
    assert D.list_id(DRAGAPULT) == D.list_id(DRAGAPULT_SHUFFLED)
    assert D.list_id(DRAGAPULT) != D.list_id(DRAGAPULT.replace("3 Dragapult ex", "2 Dragapult ex"))
    assert len(D.list_id(DRAGAPULT)) == 12


def test_auto_name_prefers_rule_box_and_partner():
    assert D.auto_name(DRAGAPULT) == "Dragapult ex"  # Duskull (2, no rule box) isn't a partner
    assert D.auto_name(GENGAR) == "Gengar ex / Zoroark ex"
    assert D.auto_name("Pokémon: 4\n4 Pikachu SVI 1\nTrainer: 1\n4 Iono PAL 185\n") == "Pikachu"
    assert D.auto_name("Trainer: 60\n60 Iono PAL 185\n") == "Decklist"
    assert D.auto_name("") == "Decklist"


# ── store ──────────────────────────────────────────────────────────────────
def test_save_same_list_keeps_name_and_moves_first():
    reset_store()
    a = D.save_decklist(DRAGAPULT, "Menu Dragapult")
    assert a["new"] is True and a["name"] == "Dragapult ex" and a["deck"] == "Dragapult ex" and a["cards"] == 60
    b = D.save_decklist(GENGAR)
    assert [e["id"] for e in D.all_decklists()] == [b["id"], a["id"]]
    D.rename_decklist(a["id"], "  My Pult  ")
    again = D.save_decklist(DRAGAPULT_SHUFFLED, "something else")
    assert again["new"] is False and again["id"] == a["id"] and again["name"] == "My Pult"
    assert again["menu_deck"] == "Menu Dragapult"  # the first capture's hint stays
    assert _latest()["id"] == a["id"] and len(D.all_decklists()) == 2
    assert not os.path.exists(D.STORE_FILE + ".tmp")  # atomic replace


def test_name_collisions_get_numbers():
    reset_store()
    first = D.save_decklist(DRAGAPULT)
    second = D.save_decklist(DRAGAPULT.replace("25 Professor's", "24 Professor's").replace("4 Ultra Ball", "5 Ultra Ball"))
    third = D.save_decklist(DRAGAPULT.replace("25 Professor's", "23 Professor's").replace("4 Ultra Ball", "6 Ultra Ball"))
    assert (first["name"], second["name"], third["name"]) == ("Dragapult ex", "Dragapult ex (2)", "Dragapult ex (3)")


def test_rename_and_delete():
    reset_store()
    e = D.save_decklist(DRAGAPULT)
    D.rename_decklist(e["id"], "   ")  # blank name: ignored
    assert _latest()["name"] == "Dragapult ex"
    D.rename_decklist(e["id"], "Pult")
    assert _latest()["name"] == "Pult" and _latest()["named_by"] == "user"
    D.delete_decklist("not-an-id")
    assert len(D.all_decklists()) == 1
    D.delete_decklist(e["id"])
    assert D.all_decklists() == [] and _latest() is None


def test_missing_or_corrupt_store():
    reset_store()
    assert D.all_decklists() == [] and D.store_mtime() is None
    for junk in ("{not json", "[1, 2]", "null", '"text"'):
        with open(D.STORE_FILE, "w", encoding="utf-8") as handle:
            handle.write(junk)
        assert D.all_decklists() == [], junk
    reset_store()


def test_old_store_formats_are_converted():
    reset_store()
    with open(D.STORE_FILE, "w", encoding="utf-8") as handle:
        json.dump({"by_deck": {"Pult": {"deck": "Pult", "text": DRAGAPULT, "captured_at": "2025-01-01 10:00:00"},
                               "Empty": {"deck": "Empty", "text": ""}}}, handle)
    lists = D.all_decklists()
    assert len(lists) == 1 and lists[0]["name"] == "Pult" and lists[0]["named_by"] == "ocr"
    assert lists[0]["id"] == D.list_id(DRAGAPULT) and lists[0]["cards"] == 60
    with open(D.STORE_FILE, "w", encoding="utf-8") as handle:
        json.dump({"latest": {"text": GENGAR}}, handle)
    assert [e["name"] for e in D.all_decklists()] == ["Gengar ex / Zoroark ex"]
    reset_store()


# ── deck <-> list links ────────────────────────────────────────────────────
def test_link_decklist_and_fallbacks():
    reset_store()
    pult = D.save_decklist(DRAGAPULT, "Dragapult")
    gengar = D.save_decklist(GENGAR, "Gengar")
    assert D.decklist_for_deck("Dragapult")["id"] == pult["id"]  # no link: the list exported on that menu deck
    assert D.decklist_for_deck("Nothing") is None
    D.link_decklist("Dragapult", gengar["id"])
    assert D.decklist_for_deck("Dragapult")["id"] == gengar["id"]  # the link wins
    D.save_decklist(DRAGAPULT)  # saving keeps the links
    assert D.decklist_for_deck("Dragapult")["id"] == gengar["id"]
    D.link_decklist("Dragapult", None)
    assert D.decklist_for_deck("Dragapult")["id"] == pult["id"]
    D.link_decklist("Never linked", None)  # removing a missing link is fine
    D.link_decklist("Dragapult", gengar["id"])
    D.delete_decklist(gengar["id"])  # a link to a deleted list falls back
    assert D.decklist_for_deck("Dragapult")["id"] == pult["id"]
    with open(D.STORE_FILE, "r", encoding="utf-8") as handle:
        assert "links" in json.load(handle)


def test_import_decklist_links_it():
    reset_store()
    e = D.import_decklist(GENGAR, "Ghosts")
    assert e["new"] is True
    assert D.decklist_for_deck("Ghosts")["id"] == e["id"]
    again = D.import_decklist(GENGAR, "Other Deck")  # same list linked to a second deck
    assert again["new"] is False
    assert D.decklist_for_deck("Other Deck")["id"] == e["id"] and D.decklist_for_deck("Ghosts")["id"] == e["id"]
    reset_store()


# ── card_usage edge cases ──────────────────────────────────────────────────
def test_card_name_edge_cases():
    assert C.card_name("Lillie’s Determination") == "Lillie's Determination"
    assert C.card_name("Basic Fire Energy") == "Fire Energy"
    assert C.card_name("Basic Foo Energy") == "Basic Foo Energy"  # not an energy type: unchanged
    assert C.card_name("Basic {X} Energy") == "X Energy"
    assert C.card_name("Double Turbo Energy") == "Double Turbo Energy"
    assert C.card_name(None) == "" and C.card_name("") == ""


def test_parse_list_headers_and_junk():
    cards = C.parse_list(GENGAR.replace("\n", "\r\n") + "\r\nTotal Cards: 60\r\nnot a card line\r\n")
    assert cards[("P", "Gengar ex")] == 3 and cards[("P", "Zoroark ex")] == 2
    assert cards[("T", "Ultra Ball")] == 38 and cards[("E", "Darkness Energy")] == 10
    assert sum(cards.values()) == 60
    assert C.parse_list("pokémon: 1\n1 Mew ex MEW 151\nENERGY: 1\n1 Basic {L} Energy MEE 4\n") == {
        ("P", "Mew ex"): 1, ("E", "Lightning Energy"): 1}
    assert C.parse_list("") == {} and C.parse_list(None) == {}
    # card lines before any header count as Pokemon
    assert C.parse_list("2 Pikachu SVI 1") == {("P", "Pikachu"): 2}


def test_decklist_and_parse_list_agree():
    assert sum(C.parse_list(DRAGAPULT).values()) == D.card_count(DRAGAPULT) == 60
    assert sum(C.parse_list(DRAGAPULT_SHUFFLED).values()) == 60


def test_similarity_and_roles():
    assert C.similarity([], {("P", "A"): 1}) == 0.0 and C.similarity([{"cat": "P", "name": "A", "per_list": 1}], {}) == 0.0
    meta = [{"cat": "P", "name": "A", "per_list": 4.0}]
    assert C.similarity(meta, {("P", "A"): 10}) == 4.0 / 60.0  # capped at the typical copies
    assert C.similarity(meta, {("T", "A"): 4}) == 0.0  # category matters
    assert (C.role(90.0), C.role(89.9), C.role(50.0), C.role(49.9)) == ("core", "common", "common", "tech")
    assert C.best_archetype([], {("P", "A"): 1}) is None


def test_classify_edge_cases():
    rows = [{"deck": "Few", "share_en": 50, "lists": 4, "cards": [{"name": "A", "cat": "P", "incl": 100}]},
            {"deck": "NoCards", "share_en": 50, "lists": 40, "cards": []}]
    assert C.classify({"A"}, rows) == []  # under 5 lists / no card data: no candidates
    assert C.classify(set(), rows) == [] and C.classify({"A"}, []) == []
    good = {"deck": "Good", "share_en": 0, "lists": 40, "cards": [{"name": "A", "cat": "P", "incl": 100}]}
    ranked = C.classify(["A", "A"], rows + [good])  # a plain list works too; zero shares don't divide by 0
    assert [r["deck"] for r, _p in ranked] == ["Good"] and abs(ranked[0][1] - 1.0) < 1e-9
    assert C.explain([], {}, rows) == ""
    assert C.popularity({"share_recent": 0.0, "share_en": 9}) == 0.0  # a recent 0 is a real 0
    assert C.popularity({"share": 2}) == 2 and C.popularity({}) == 0.0


def test_log_card_counts_edge_cases():
    C.set_known_cards(["Dreepy", "Ab", ""])  # names of 2 chars or less are ignored
    assert C._known_card_pattern().pattern.count("Ab") == 0
    log = "\n".join(["opp played Dreepy to the Bench."] * 6 + [
        "opp played Buddy-Buddy Poffin.",
        "- opp drew 2 cards and played them to the Bench.",
        "   • Duskull, Duskull",
        "opp evolved Duskull to Dusclops on the Bench.",
        "opp attached Basic Psychic Energy to Dusclops on the Bench.",
        "me played Pikachu to the Bench.",
        "   • Raichu",
        "opp's Dreepy used Petty Grudge on me's Pikachu for 10 damage.",
    ])
    counts = C.log_card_counts(log, "opp", "me")
    assert counts["Dreepy"] == C.MAX_COPIES  # capped
    assert counts["Duskull"] == 2 and counts["Dusclops"] == 1 and counts["Psychic Energy"] == 1
    assert "Pikachu" not in counts and "Raichu" not in counts
    assert C.log_card_counts(log, "", "me") == {} and C.log_card_counts("", "opp") == {}
    C.set_known_cards([])
    assert C._known_card_pattern() is None


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failures else 0)
