"""Tests for deck_share.py (run: python test_deck_share.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decklists as D
import deck_share as S

LIST = """Pokémon: 13
2 N's Zorua JTG 97
1 Pecharunt ex SFA 95
2 Mega Gengar ex PFL 56
1 N's Zoroark ex JTG 175
2 Haunter MEP 27
2 Gengar ex 30C 90
1 Meowth ex POR 121
1 Munkidori SFA 72
1 Fezandipiti ex SFA 92

Trainer: 30
3 Nighttime Mine ASC 197
4 Lillie's Determination MEG 119
3 Rare Candy MEG 175
3 Night Stretcher SSP 251
4 Buddy-Buddy Poffin TWM 223
3 Janine's Secret Art SFA 88
4 Ultra Ball CRZ 146
4 Boss's Orders PAL 248
2 Totally Made Up Card ZZZ 999

Energy: 17
13 Basic {D} Energy MEE 7
4 Shadowy {D} Energy PBL 83

Total Cards: 60"""


def same(a, b):
    return D.list_id(a) == D.list_id(b)


def test_round_trip_and_size():
    assert D.is_ptcgl_decklist(LIST)
    url = S.share_url(LIST, "Gengar / Zoroark")
    text, name = S.parse(url)
    assert same(text, LIST) and name == "Gengar / Zoroark"
    assert len(url.split("#")[1]) < 160, url  # one made-up card is spelled out


def test_counts_above_seven_and_sections_kept():
    text, _ = S.parse(S.share_url(LIST))
    assert "13 Basic {D} Energy MEE 7" in text
    assert text.index("Trainer:") < text.index("Energy:") and "Total Cards: 60" in text
    assert text.split("Energy:")[0].count("Totally Made Up Card ZZZ 999") == 1


def test_app_link_and_bare_token():
    app = S.share_url(LIST, "X", web=False)
    assert app.startswith("ptcglmonitor://d#")
    assert same(S.parse(app)[0], LIST)
    token = S.encode(LIST)
    assert same(S.parse(token)[0], LIST)


def test_deflated_version_for_unknown_cards():
    lines = "\n".join(f"4 Imaginary Card Number {i} QQQ {i}" for i in range(1, 16))
    text = f"Pokémon: 60\n{lines}\n\nTrainer: 0\n\nEnergy: 0\n\nTotal Cards: 60"
    token = S.encode(text)
    assert token[0] == "b"
    assert same(S.decode(token), text)


def test_rejects_junk():
    for bad in ("", "hello", "https://example.com/#zzzz", "a", "a!!!!", "aAAAA", "b" + "A" * 40,
                S.WEB_BASE + "#a" + "_" * 5000):
        try:
            S.parse(bad)
        except S.ShareError:
            continue
        raise AssertionError(f"accepted {bad[:40]!r}")


def test_newer_table_message():
    out = bytearray()
    S._varint((10_000 * 2) * 8 + 1, out)
    try:
        S.decode("a" + S._b64(bytes(out)))
    except S.ShareError as exc:
        assert "newer" in str(exc)
    else:
        raise AssertionError("accepted")


def test_literal_cannot_inject_lines():
    card = b"Fake\nTrainer: 99 SET 1"
    out = bytearray()
    S._varint((len(card) * 2 + 1) * 8 + 4, out)
    out += card
    try:
        S.decode("a" + S._b64(bytes(out)))
    except S.ShareError:
        pass
    else:
        raise AssertionError("accepted a literal with a line break")


def test_name_is_cleaned():
    url = S.share_url(LIST, "<b>" + "x" * 80 + "\n")
    _text, name = S.parse(url)
    assert "<" not in name and len(name) <= S.MAX_NAME


def test_looks_like_link():
    assert S.looks_like_link(S.share_url(LIST))
    assert S.looks_like_link(S.share_url(LIST, web=False))
    assert not S.looks_like_link("https://example.com/#a123") and not S.looks_like_link(LIST)


def test_web_page_decodes_the_same():
    """docs/d/index.html's decoder (run in Node) gives the same lists."""
    import json
    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node")
    if not node:
        print("SKIP node not installed")
        return
    lines = "\n".join(f"4 Imaginary Card Number {i} QQQ {i}" for i in range(1, 16))
    texts = [LIST, f"Pokémon: 60\n{lines}\n\nTrainer: 0\n\nEnergy: 0\n\nTotal Cards: 60"]
    cases = [{"token": S.encode(t), "text": S.decode(S.encode(t))} for t in texts]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(cases, handle, ensure_ascii=False)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        run = subprocess.run([node, os.path.join(here, "share_page_check.mjs"), handle.name],
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert run.returncode == 0, run.stdout + run.stderr
    finally:
        os.remove(handle.name)


def test_docs_table_matches_app_table():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "docs", "d", "cards_v1.txt"), encoding="utf-8") as a, \
            open(S.TABLE_FILE, encoding="utf-8") as b:
        assert a.read() == b.read()


def test_table_is_frozen_shape():
    rows, index = S.table()
    assert len(rows) >= 840 and len(index) == len(rows)
    assert rows[0] == "Boss's Orders MEG 114"


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
