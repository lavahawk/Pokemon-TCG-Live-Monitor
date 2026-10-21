"""Tests for ptcgl_import.py's matching logic (run: python test_ptcgl_import.py).
Nothing here touches the game, the mouse or the screen."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ptcgl_import as P


def word(text, x, y, w=60, h=20):
    return (text, 90.0, (x, y, w, h))


def test_similar_tolerates_ocr_noise():
    assert P._similar("DECKS", "decks") == 1.0
    assert P._similar("0WNED", "OWNED") >= 0.8
    assert P._similar("PROFILE", "DECKS") < 0.5


def test_phrase_needs_words_in_order_on_one_line():
    words = [word("CREATE", 100, 500), word("A", 165, 500, 15), word("DECK", 185, 500),
             word("DECK", 100, 700)]
    point = P.Screen._find("CREATE A DECK", words, 0.8)
    assert point and 100 < point[0] < 245 and 500 <= point[1] <= 520
    # same words on different lines don't make the phrase
    assert P.Screen._find("CREATE A DECK", [word("CREATE", 100, 500), word("A", 165, 600, 15),
                                             word("DECK", 185, 700)], 0.8) is None


def test_single_word_and_best_match():
    words = [word("DECK", 10, 10), word("DECKS", 300, 40)]
    assert P.Screen._find("DECKS", words, 0.8) == (330, 50)


def test_minimize_request_is_taken_once():
    original = P.MINIMIZE_FILE
    P.MINIMIZE_FILE = os.path.join(tempfile.gettempdir(), "test_minimize_dashboard")
    try:
        assert not P.take_minimize_request()
        P.request_minimize_dashboard()
        assert P.take_minimize_request()
        assert not P.take_minimize_request()
    finally:
        P.MINIMIZE_FILE = original


def test_regions_are_fractions():
    for region in (P.NAV, P.DECK_GRID, P.DIALOG, P.RIGHT_PANEL, P.EDITOR):
        x0, y0, x1, y1 = region
        assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1


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
