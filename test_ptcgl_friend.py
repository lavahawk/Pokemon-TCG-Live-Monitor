"""Tests for ptcgl_friend.py (run: python test_ptcgl_friend.py). Nothing is
clicked; the once-per-match record lives in a temp folder."""
import atexit
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ptcgl_friend as F

TMP = tempfile.mkdtemp(prefix="ptcgl_friend_test_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
F.DONE_FILE = os.path.join(TMP, ".friend_requests.json")


def test_opponent_from_dashboard_link():
    assert F.opponent_from_match_link("R1 vs Bob") == "Bob"
    assert F.opponent_from_match_link("R3 vs\nAsh Ketchum\nActive Match") == "Ash Ketchum"
    assert F.opponent_from_match_link("R2 vs. Misty_99 Active Match") == "Misty_99"
    assert F.opponent_from_match_link("R4 vs Brock (2-1)") == "Brock"
    assert F.opponent_from_match_link("Active Match") == ""
    assert F.opponent_from_match_link("") == ""


def test_friend_request_claimed_once_per_match():
    assert F._claim("url1|bob")
    assert not F._claim("url1|bob")
    assert F._claim("url2|bob")  # same player, next round's match


def test_disabled_setting_only_copies():
    calls = []
    F.copy_to_clipboard = lambda text: calls.append(text) or True
    F.auto_add_enabled = lambda: False
    F.handle_new_opponent("Bob", "url9")
    assert calls == ["Bob"] and F._claim("url9|bob")  # nothing was claimed


class _Screen:
    size = (1920, 1080)


def _adder(name_box_reads, red_checks):
    """A FriendAdder with the screen faked: SEND stays red for red_checks
    looks, the name box reads name_box_reads in turn."""
    a = object.__new__(F.FriendAdder)
    a.friend, a.clicks, a.said = "Bob", [], []
    reads = list(name_box_reads)
    reds = [red_checks]
    a._screen = lambda: _Screen()
    a._click = lambda screen, point: a.clicks.append(point)
    a._say = a.said.append
    a._progress = lambda message, value: None

    def send(timeout):
        reds[0] -= 1
        return _Screen(), ((1, 1) if reds[0] >= 0 else None)
    a._wait_send_enabled = send
    a._band_text = lambda screen, band: ((reads.pop(0) if len(reads) > 1 else reads[0]), (0, 0))
    return a


def test_backs_out_after_sending():
    a = _adder(["", ""], red_checks=2)   # SEND greys after 2 looks, box gone after the click
    a._back_out()
    assert a.clicks == [(0.040 * 1080, 0.1115 * 1080)], a.clicks
    assert not a.said, a.said


def test_back_out_never_fails_the_add():
    a = _adder(["ENTER SCREEN NAME"], red_checks=0)   # the box stays: say so, no Esc
    a._back_out()
    assert len(a.clicks) == 1 and "couldn't close" in a.said[-1], a.said
    b = _adder([""], red_checks=0)
    b._click = lambda screen, point: (_ for _ in ()).throw(RuntimeError("game gone"))
    b._back_out()   # swallowed: the request was already sent


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{'All passed' if not failures else f'{failures} failed'}")
    sys.exit(1 if failures else 0)
