"""Tests for the decklist auto-capture (run: python -m pytest test_decklist_capture.py, or python test_decklist_capture.py)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import card_usage
import decklists
from card_usage import card_prints, format_list, legal_copies, log_card_counts, log_deck_counts, merge_seen

# A 60-card deck: 16 Pokemon, 34 Trainers (one ACE SPEC), 10 Energy (7 basic).
DECK = {
    "Gastly": 4, "Haunter": 2, "Gengar ex": 3, "Dunsparce": 2, "Dudunsparce": 2, "Fezandipiti ex": 1,
    "Pecharunt ex": 1, "Mega Gengar ex": 1,
    "Ultra Ball": 4, "Buddy-Buddy Poffin": 4, "Rare Candy": 4, "Poké Pad": 4, "Night Stretcher": 3,
    "Lillie's Determination": 4, "Boss's Orders": 2, "Janine's Secret Art": 2, "Dawn": 2,
    "Nighttime Mine": 3, "Unfair Stamp": 1, "Team Rocket's Petrel": 1,
    "Darkness Energy": 7, "Shadowy Darkness Energy": 3,
}
PRINTS = {name: ("P", "SET", str(i)) for i, name in enumerate(list(DECK)[:8], 1)}
PRINTS.update({name: ("T", "TRN", str(i)) for i, name in enumerate(list(DECK)[8:20], 1)})
PRINTS.update({"Darkness Energy": ("E", "MEE", "7"), "Shadowy Darkness Energy": ("E", "PBL", "83")})


def split(deck, parts):
    """The deck shown over `parts` games: each card's copies all seen in one game."""
    games = [{} for _ in range(parts)]
    for i, (name, n) in enumerate(sorted(deck.items())):
        games[i % parts][name] = n
    return games


def test_deck_is_sixty():
    assert sum(DECK.values()) == 60


def test_legal_copies():
    assert legal_copies("Darkness Energy", 9) == 9          # basic Energy: any number
    assert legal_copies("Shadowy Darkness Energy", 6) == 4  # special Energy: max 4
    assert legal_copies("Gastly", 6) == 4                   # replayed after a recovery
    assert legal_copies("Unfair Stamp", 2) == 1             # ACE SPEC: one copy
    assert legal_copies("Ultra Ball", 2) == 2


SOME = {"Gastly": 2, "Ultra Ball": 1, "Darkness Energy": 3}  # a later game: nothing new


def test_max_per_card_across_games_reaches_sixty():
    games = split(DECK, 4) + [dict(SOME), {"Gastly": 3, "Dawn": 1}, {"Darkness Energy": 5}]
    result = merge_seen(games)
    assert result["complete"] and result["total"] == 60 and result["cards"] == DECK
    assert result["games"] == 7 and result["confirmed"] == 3 and result["stop"] is None


def test_sixty_needs_confirming_games():
    result = merge_seen(split(DECK, 4) + [dict(SOME)] * 2)
    assert result["total"] == 60 and result["confirmed"] == 2 and not result["complete"]
    assert merge_seen(split(DECK, 4) + [dict(SOME)] * 2, confirm=2)["complete"]


def test_landing_on_sixty_then_overflowing_is_not_complete():
    # 59 real cards seen + an old version's tech = 60, then an older game overflows
    seen = dict(DECK, **{"Dawn": 1})
    games = split(seen, 3) + [{"Energy Recycler": 1}, {"Prism Tower": 1}]
    result = merge_seen(games)
    assert result["total"] == 60 and result["stop"] == "61 cards > 60" and not result["complete"]


def test_partial_deck_is_not_complete():
    partial = dict(DECK)
    del partial["Dawn"]
    result = merge_seen(split(partial, 3) + [dict(SOME)] * 5)
    assert not result["complete"] and result["total"] == 58


def test_over_counted_cards_are_capped():
    games = split(DECK, 2)
    games[0]["Gastly"] = 7       # evolved / replayed: still 4
    games[1]["Unfair Stamp"] = 2  # recovered ACE SPEC: still 1
    result = merge_seen(games, confirm=0)
    assert result["cards"]["Gastly"] == 4 and result["cards"]["Unfair Stamp"] == 1
    assert result["complete"]


def test_edited_deck_stops_at_older_games():
    newest = split(DECK, 3) + [dict(SOME)] * 3
    old = {"Iron Hands ex": 3, "Electric Generator": 4, "Lightning Energy": 8}  # an older version
    result = merge_seen(newest + [old])
    assert result["complete"] and result["games"] == 6
    assert result["stop"] == "75 cards > 60" and "Iron Hands ex" not in result["cards"]


def test_two_ace_specs_stop():
    games = split(DECK, 2) + [{"Prime Catcher": 1}]
    result = merge_seen(games)
    assert result["stop"].startswith("two ACE SPECs") and "Prime Catcher" not in result["cards"]


LOG = """Me played Gastly to the Bench.
Me played Gastly to the Active Spot.
Opp played Ultra Ball.
Me played Rare Candy.
- Me evolved Gastly to Mega Gengar ex on the Bench.
Me's Mega Gengar ex was Knocked Out!
Me played Night Stretcher.
- Me moved Me's Mega Gengar ex to their hand.
Me played Rare Candy.
- Me evolved Gastly to Mega Gengar ex in the Active Spot.
Me evolved Dunsparce to Dudunsparce on the Bench.
Me played Dudunsparce.
- Me drew 3 cards.
   • Gengar ex, Basic Darkness Energy, Poké Pad
- Me shuffled 2 cards into their deck.
   • Dudunsparce, Dunsparce
Me played Dunsparce to the Bench.
Me evolved Dunsparce to Dudunsparce on the Bench.
Me's Dudunsparce used Run Away Draw.
- Me shuffled 2 cards into their deck.
   • Dudunsparce, Dunsparce
Me played Lillie's Determination.
- Me shuffled 3 cards into their deck.
   • Gastly, Gastly, Gastly
Me attached Basic Darkness Energy to Gastly on the Bench.
Me attached Basic Darkness Energy to Gastly on the Bench.
Me played Energy Recycler.
- Me shuffled Basic Darkness Energy into their deck.
Me attached Basic Darkness Energy to Gastly on the Bench.
Me drew 2 cards and played them to the Bench.
   • Gastly, Fezandipiti ex
Opp played Prism Tower to the Stadium spot.
Me played Prism Tower.
- Me drew 2 cards.
"""


def test_log_deck_counts_ignores_replays():
    counts = log_deck_counts(LOG, "Me", "Opp")
    assert log_card_counts(LOG, "Me", "Opp", cap=None)["Mega Gengar ex"] == 2
    assert counts["Mega Gengar ex"] == 1      # Night Stretcher took it back, then replayed
    assert counts["Dudunsparce"] == 1 and counts["Dunsparce"] == 1  # shuffled back by its ability
    assert counts["Gastly"] == 3              # Lillie's shuffles the hand, not cards in play
    assert counts["Darkness Energy"] == 2     # Energy Recycler put one back
    assert counts["Rare Candy"] == 2 and counts["Night Stretcher"] == 1 and counts["Fezandipiti ex"] == 1
    assert counts["Gengar ex"] == 1 and "Ultra Ball" not in counts  # shown only; the opponent's card
    assert "Prism Tower" not in counts        # used the opponent's Stadium, not a card of ours


def test_format_list_round_trips():
    text, missing = format_list(DECK, PRINTS)
    assert missing == []
    assert "7 Basic {D} Energy MEE 7" in text and text.endswith("Total Cards: 60")
    assert decklists.is_ptcgl_decklist(text) and decklists.card_count(text) == 60
    parsed = card_usage.parse_list(text)
    assert {name: n for (_cat, name), n in parsed.items()} == DECK
    assert parsed[("T", "Unfair Stamp")] == 1 and parsed[("E", "Darkness Energy")] == 7


def test_format_list_needs_every_print():
    text, missing = format_list(dict(DECK, **{"Mystery Card": 1}), PRINTS)
    assert text is None and missing == ["Mystery Card"]


def test_card_prints_prefers_your_exports():
    rows = [{"cards": [{"name": "Gastly", "cat": "P", "set": "AAA", "number": "1", "incl": 90},
                       {"name": "Ultra Ball", "cat": "T", "set": "SVI", "number": "196", "incl": 99}]}]
    mine = "Pokémon: 4\n4 Gastly POR 48\n\nTrainer: 1\n1 Rare Candy MEG 175\n\nEnergy: 1\n1 Basic {D} Energy MEE 7\n"
    prints = card_prints(rows, [mine])
    assert prints["Gastly"] == ("P", "POR", "48")
    assert prints["Rare Candy"] == ("T", "MEG", "175")
    assert prints["Darkness Energy"] == ("E", "MEE", "7")
    assert prints["Ultra Ball"] == ("T", "SVI", "196")


def test_log_counts_uncapped_for_basic_energy():
    log = "\n".join(["Me attached Basic Darkness Energy to Gastly in the Active Spot."] * 6)
    assert log_card_counts(log, "Me", "Opp")["Darkness Energy"] == 4
    assert log_card_counts(log, "Me", "Opp", cap=None)["Darkness Energy"] == 6


def test_auto_capture_storage():
    text, _ = format_list(DECK, PRINTS)
    other, _ = format_list(dict(DECK, **{"Dawn": 1, "Ultra Ball": 4, "Darkness Energy": 8}), PRINTS)
    saved = decklists.STORE_FILE
    with tempfile.TemporaryDirectory() as tmp:
        decklists.STORE_FILE = os.path.join(tmp, "lists.json")
        try:
            entry = decklists.auto_capture("Gengar", text, games=5)
            assert entry and entry["auto_captured"] == {"deck": "Gengar", "games": 5}
            assert decklists.decklist_for_deck("Gengar")["id"] == entry["id"]
            assert decklists.is_auto_linked("Gengar")
            # a newer complete capture replaces the old auto list
            newer = decklists.auto_capture("Gengar", other, games=6)
            assert newer["id"] != entry["id"] and decklists.decklist_for_deck("Gengar")["id"] == newer["id"]
            assert entry["id"] not in [e["id"] for e in decklists.all_decklists()]
            # your own link is never overwritten
            mine = decklists.save_decklist(text + "\n", "Elsewhere")
            decklists.link_decklist("Gengar", mine["id"])
            assert not decklists.is_auto_linked("Gengar")
            assert decklists.auto_capture("Gengar", other) is None
            assert decklists.decklist_for_deck("Gengar")["id"] == mine["id"]
            # a list you exported while the deck was on the menu counts as yours
            third, _ = format_list(dict(DECK, **{"Dawn": 3, "Darkness Energy": 6}), PRINTS)
            decklists.save_decklist(third, "Dragapult")
            assert decklists.auto_capture("Dragapult", text) is None
            # unlinking an auto list turns auto-capture off for that deck
            assert decklists.auto_capture("Zoroark", text)
            decklists.link_decklist("Zoroark", None)
            assert decklists.auto_capture("Zoroark", text) is None
        finally:
            decklists.STORE_FILE = saved


def test_auto_capture_keeps_older_store_lists():
    import json
    text, _ = format_list(DECK, PRINTS)
    saved = decklists.STORE_FILE
    with tempfile.TemporaryDirectory() as tmp:
        decklists.STORE_FILE = os.path.join(tmp, "lists.json")
        try:
            with open(decklists.STORE_FILE, "w", encoding="utf-8") as handle:
                json.dump({"by_deck": {"Gengar": {"deck": "Gengar", "text": text}}}, handle)
            assert decklists.auto_capture("Gengar", text) is None  # your export, named after the deck
        finally:
            decklists.STORE_FILE = saved


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failures else 0)
