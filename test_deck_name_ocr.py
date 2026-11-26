"""Deck-name OCR on the main menu: real captures and made-up names on the
game's dotted panel, at 1920x1080 and smaller windows."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

import RankDetector as R  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "test_fixtures")
REAL = os.path.join(FIX, "deck_name_gengar_testing.png")   # captured at 1942x1136
OTHER = os.path.join(FIX, "deck_name_other_screen.png")     # the box over a battle


def _scaled(img, window_h):
    s = window_h / 1136.0
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.BICUBIC)


def _synth(name, window_h):
    """A name drawn on the real dotted panel, as the padded capture sees it."""
    s = window_h / 1136.0
    panel = Image.open(REAL).convert("RGB").crop((0, 0, 48, 24))
    w, h = round(219 * 1.7 * s), round(24 * 1.6 * s)
    img = Image.new("RGB", (w, h))
    for x in range(0, w, max(1, round(48 * s))):
        img.paste(panel.resize((max(1, round(48 * s)), h)), (x, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "bahnschrift.ttf"),
                              max(8, round(19 * s)))
    draw.text(((w - draw.textlength(name, font=font)) / 2, h / 2 - 10 * s), name, fill=(98, 98, 104), font=font)
    return img.filter(ImageFilter.GaussianBlur(0.35 * s))


def test_real_capture_at_each_size():
    img = Image.open(REAL).convert("RGB")
    for window_h in (1136, 1080, 900):
        text, conf = R.read_deck_name_image(_scaled(img, window_h))
        assert text == "Gengar Testing", (window_h, text, conf)


def test_box_reaching_past_the_panel():
    """25 Nov 2026 at 1920x1080: the padded box takes in the panel's red
    edges and the rim above the name; every menu read came back empty."""
    img = Image.open(os.path.join(FIX, "deck_name_drill_3_panel_edges.png")).convert("RGB")
    text, conf = R.read_deck_name_image(img)
    assert text == "Drill 3", (text, conf)


def test_other_screen_is_not_a_deck_name():
    text, conf = R.read_deck_name_image(Image.open(OTHER).convert("RGB"))
    assert text is None, (text, conf)


def test_long_names_with_numbers_at_1080():
    for name in ("Pult Hammers NAIC 2026", "Dengo Pult ATL NEW ED", "Kellers Pult Baltimore",
                 "Miraidon 3.0", "Grimmsnarl Froslass"):
        text, conf = R.read_deck_name_image(_synth(name, 1080))
        assert text == name, (name, text, conf)


def test_snaps_to_a_known_name():
    assert R.snap_deck_name("Oragapult Ousknoir", ["Dragapult Dusknoir", "Dragapult"]) == "Dragapult Dusknoir"


if __name__ == "__main__":
    passed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            passed += 1
            print(f"PASS {name}")
    print(f"{passed} passed")
