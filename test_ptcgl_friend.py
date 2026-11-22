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


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{'All passed' if not failures else f'{failures} failed'}")
    sys.exit(1 if failures else 0)
