"""Rank is read only on the Home screen: the nav bar's words are on every
menu screen, the lit (yellow) tab says which one is up (run: python
test_home_screen.py). Crops captured from the game at 1942x1136."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image  # noqa: E402

import RankDetector as R  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_fixtures")


def crop(name):
    return Image.open(os.path.join(FIX, name)).convert("RGB")


def test_home_tab_lit():
    assert R.home_tab_active(crop("menu_text_home.png")) is True


def test_decks_screen_is_not_home():
    # 24 Nov 2026: this screen passed as the main menu; a card read as rank 1.
    assert R.home_tab_active(crop("menu_text_decks.png")) is False


def test_no_highlight_is_unknown():
    assert R.home_tab_active(Image.new("RGB", (245, 90), (10, 10, 10))) is None


def test_menu_check_needs_home_but_not_the_deck_name():
    class Fake(R.RankDetector):
        def __init__(self, nav, rank, deck):
            self.regions = {"menu_text": {}, "my_deck_name": {}}
            self._nav, self._rank, self._deck = nav, rank, deck

        def validate_screen_by_text(self, region, words, partial_match=True):
            return True   # the nav words are on every screen

        def capture_region(self, region, **_):
            return crop(self._nav)

        def extract_rank(self, debug=False):
            return self._rank

        def read_deck_name(self, debug=False):
            return self._deck

    assert Fake("menu_text_home.png", 489, "Drill 3").is_on_main_menu() is True
    assert Fake("menu_text_home.png", 489, None).is_on_main_menu() is True      # deck name missed: rank still kept
    d = Fake("menu_text_decks.png", 1, "aay")
    assert d.is_on_main_menu() is False and d.last_menu_checks.get("home_tab") is False
    assert Fake("menu_text_home.png", None, "Drill 3").is_on_main_menu() is False


def test_deck_name_drill_3_reads():
    assert R.read_deck_name_image(crop("deck_name_drill_3.png"))[0] == "Drill 3"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
