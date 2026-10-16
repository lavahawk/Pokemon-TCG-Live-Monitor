"""Tests for the decklist tools in decklists.py: list parsing, card image URLs,
TCGplayer product lookup (stubbed tcgcsv) and Mass Entry URLs
(run: python test_decklist_tools.py). No network; cache in a temp dir."""
import atexit
import os
import shutil
import sys
import tempfile
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decklists as D

TMP = tempfile.mkdtemp(prefix="decklist_tools_test_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
D.TCGCSV_DIR = TMP

LIST = """Pokémon: 3
4 Dreepy TWM 128
1 Munkidori TWM 95
1 Pecharunt PR-SV 149

Trainer: 2
4 Crushing Hammer SSH 159
1 Judge LOT 209

Energy: 1
5 Basic {D} Energy MEE 7

Total Cards: 16
"""

CATALOGUE = {
    "groups": {"results": [{"groupId": 1, "abbreviation": "TWM"}, {"groupId": 2, "abbreviation": "SWSH01"},
                           {"groupId": 3, "abbreviation": "SM8"}, {"groupId": 4, "abbreviation": "MEE"}]},
    "1/products": {"results": [
        {"productId": 550172, "extendedData": [{"name": "Number", "value": "128/167"}]},
        {"productId": 550139, "extendedData": [{"name": "Number", "value": "095/167"}]}]},
    "2/products": {"results": [{"productId": 208485, "extendedData": [{"name": "Number", "value": "159/202"}]}]},
    "3/products": {"results": [{"productId": 179010, "extendedData": [{"name": "Number", "value": "209/214"}]}]},
    "4/products": {"results": [{"productId": 656269, "extendedData": [{"name": "Number", "value": "7"}]}]},
}


def fake_fetch(url):
    return CATALOGUE[url.split("/tcgplayer/3/", 1)[1]]


def test_list_lines_sections_and_counts():
    cards = D.list_lines(LIST)
    assert [c["section"] for c in cards] == ["Pokémon"] * 3 + ["Trainer"] * 2 + ["Energy"]
    assert sum(c["qty"] for c in cards) == 16
    assert cards[2]["set"] == "PR-SV" and cards[2]["number"] == "149"


def test_card_image_urls():
    assert D.card_image_url("TWM", "95").endswith("/TWM/TWM_095_R_EN_SM.png")
    assert "/SVP/SVP_149_" in D.card_image_url("PR-SV", "149")


def test_product_ids_by_set_and_number():
    ids = D.tcgplayer_product_ids(LIST, fetch=fake_fetch)
    assert ids[("TWM", "128")] == 550172 and ids[("TWM", "95")] == 550139  # "095/167" == "95"
    assert ids[("SSH", "159")] == 208485 and ids[("LOT", "209")] == 179010  # PTCGL -> TCGplayer codes
    assert ids[("MEE", "7")] == 656269
    assert ("PR-SV", "149") not in ids  # no such group in the stub


def test_lines_exact_products_else_name():
    ids = D.tcgplayer_product_ids(LIST, fetch=fake_fetch)
    lines = D.tcgplayer_lines(LIST, ids)
    assert lines[0] == "4-550172" and lines[-1] == "5-656269"
    assert lines[2] == "1 Pecharunt [SVP]"


def test_url_and_affiliate_wrap():
    ids = D.tcgplayer_product_ids(LIST, fetch=fake_fetch)
    url = D.tcgplayer_url(LIST, ids, affiliate="")
    query = parse_qs(urlparse(url).query)
    assert query["productline"] == ["Pokemon"] and query["c"][0].split("||")[0] == "4-550172"
    wrapped = D.tcgplayer_url(LIST, ids, affiliate="https://partner.tcgplayer.com/c/1/1830156/21018")
    assert wrapped.startswith("https://partner.tcgplayer.com/c/1/1830156/21018?u=")
    assert unquote(parse_qs(urlparse(wrapped).query)["u"][0]) == unquote(url) or parse_qs(urlparse(wrapped).query)["u"][0] == url


def test_offline_uses_stale_cache():
    D.tcgplayer_product_ids(LIST, fetch=fake_fetch)  # fills the cache

    def offline(_url):
        raise OSError("offline")
    old = D.TCGCSV_MAX_AGE_S
    D.TCGCSV_MAX_AGE_S = -1  # everything counts as stale
    try:
        ids = D.tcgplayer_product_ids(LIST, fetch=offline)
    finally:
        D.TCGCSV_MAX_AGE_S = old
    assert ids[("TWM", "128")] == 550172


def test_set_codes_starting_with_a_digit():
    cards = D.list_lines("Pok\u00e9mon: 1\n3 Gengar ex 30C 90\n")
    assert len(cards) == 1 and cards[0]["set"] == "30C" and cards[0]["qty"] == 3


def test_limitless_picture_posts_and_caches():
    D.BASE_DIR = TMP  # the picture cache goes under BASE_DIR
    calls = []
    png = b"\x89PNG" + b"0" * 2000

    def post(url, fields):
        calls.append((url, dict(fields)))
        if url.endswith("imggen"):
            return '<input type="hidden" name="data" value="4:TWM-128~int*en">'
        return png
    assert D.limitless_picture(LIST, normalized=True, post=post) == png
    assert calls[0][1].get("standardize") == "on" and calls[1][1]["data"] == "4:TWM-128~int*en"
    assert D.limitless_picture(LIST, normalized=True, post=post) == png and len(calls) == 2  # cached


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
