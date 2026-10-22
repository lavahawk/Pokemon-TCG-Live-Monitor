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


def test_import_links_the_list_to_the_deck():
    """A shared deck lands in the monitor: saved, named, and linked to the
    deck's name (temp store; the user's .decklists.json is never touched)."""
    import tempfile
    import deck_link
    saved = D.STORE_FILE
    with tempfile.TemporaryDirectory() as tmp:
        D.STORE_FILE = os.path.join(tmp, ".decklists.json")
        try:
            entry, had = deck_link.import_list(LIST, "Gengar Box")
            assert not had and entry["name"] == "Gengar Box"
            assert D.decklist_for_deck("Gengar Box")["id"] == entry["id"]
            again, had = deck_link.import_list(LIST, "Gengar Box")
            assert had and again["id"] == entry["id"]
        finally:
            D.STORE_FILE = saved


def test_copied_link_is_offered_once_and_own_links_never():
    """The monitor's clipboard watch: someone else's link opens the import box
    once; your own links and damaged links never (temp files, no box opens)."""
    import tempfile
    import TCGLiveMonitor as M
    saved = (S.OWN_FILE, S.SEEN_FILE, M.subprocess.Popen)
    opened = []
    with tempfile.TemporaryDirectory() as tmp:
        S.OWN_FILE, S.SEEN_FILE = os.path.join(tmp, "own"), os.path.join(tmp, "seen")
        M.subprocess.Popen = lambda args, **kw: opened.append(args[-1])
        try:
            monitor = M.Monitor.__new__(M.Monitor)
            theirs = S.share_url(LIST, "Gengar Testing")
            mine = S.share_url(LIST.replace("2 Haunter MEP 27", "3 Haunter MEP 27"), "Mine")
            S.remember_own(mine)
            assert monitor.handle_link(theirs) and opened == [theirs]
            assert monitor.handle_link(theirs) and opened == [theirs]  # asked once
            assert monitor.handle_link(mine) and opened == [theirs]  # yours: skipped
            assert monitor.handle_link(S.WEB_BASE + "#azzzz~x") and opened == [theirs]  # damaged
            assert not monitor.handle_link("just some text")
        finally:
            S.OWN_FILE, S.SEEN_FILE, M.subprocess.Popen = saved


def test_a_deck_you_already_have_is_not_offered():
    """Same cards and same name (its own, or a deck it's linked to) = yours:
    no import box, from the clipboard or a clicked link (temp store)."""
    import tempfile
    import TCGLiveMonitor as M
    saved = (D.STORE_FILE, S.OWN_FILE, S.SEEN_FILE, M.subprocess.Popen)
    opened = []
    with tempfile.TemporaryDirectory() as tmp:
        D.STORE_FILE = os.path.join(tmp, ".decklists.json")
        S.OWN_FILE, S.SEEN_FILE = os.path.join(tmp, "own"), os.path.join(tmp, "seen")
        M.subprocess.Popen = lambda args, **kw: opened.append(args[-1])
        try:
            entry = D.save_decklist(LIST)
            D.rename_decklist(entry["id"], "Gengar Testing")
            assert D.stored_copy(LIST, "Gengar Testing")["id"] == entry["id"]
            assert D.stored_copy(LIST, "  gengar testing ") is not None  # any case / spacing
            assert D.stored_copy(LIST) is not None  # no name in the link: the cards decide
            assert D.stored_copy(LIST, "Someone else's name") is None  # same cards, other name: offered
            assert D.stored_copy(LIST.replace("2 Haunter MEP 27", "3 Haunter MEP 27"), "Gengar Testing") is None
            D.link_decklist("Dragapult Box", entry["id"])
            assert D.stored_copy(LIST, "Dragapult Box") is not None  # the deck it's linked to counts
            monitor = M.Monitor.__new__(M.Monitor)
            assert monitor.handle_link(S.share_url(LIST, "Gengar Testing")) and opened == []
            assert monitor.handle_link(S.share_url(LIST, "Other name")) and len(opened) == 1
        finally:
            D.STORE_FILE, S.OWN_FILE, S.SEEN_FILE, M.subprocess.Popen = saved


def test_one_import_box_per_link():
    import deck_link
    link = S.share_url(LIST, "Lock test")
    assert deck_link.first_box_for(link)
    if sys.platform == "win32":
        # another process (the second box) finds this link's mutex taken
        import subprocess
        code = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[2]); import deck_link; "
                               "sys.exit(0 if deck_link.first_box_for(sys.argv[1]) else 3)",
                               link, os.path.dirname(os.path.abspath(__file__))]).returncode
        assert code == 3, code


def test_import_progress_only_moves_forward():
    import deck_link
    value = deck_link.step_progress("Opening Decks…")
    assert 0 < value < deck_link.step_progress("Creating the deck…", value)
    assert deck_link.step_progress("Waiting for Pokémon TCG Live's main menu…", 0.5) == 0.5
    assert deck_link.step_progress("something new", 0.3) == 0.3


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
