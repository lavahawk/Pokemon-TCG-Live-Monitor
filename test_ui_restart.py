"""Tests for ui_restart.py (run: python test_ui_restart.py). The note lives in
a temp folder; nothing is launched."""
import atexit
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ui_restart as R

TMP = tempfile.mkdtemp(prefix="ui_restart_test_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
R.MARKER = os.path.join(TMP, ".ui_restart.json")


def test_note_is_read_once():
    R.request("Advanced")
    assert R.pending()
    assert R.take()["tab"] == "Advanced"
    assert not R.pending() and R.take() is None


def test_stale_or_broken_note_is_ignored():
    with open(R.MARKER, "w", encoding="utf-8") as handle:
        json.dump({"time": time.time() - 3600, "tab": "Stats"}, handle)
    old = time.time() - 3600
    os.utime(R.MARKER, (old, old))
    assert not R.pending() and R.take() is None and not os.path.exists(R.MARKER)
    with open(R.MARKER, "w", encoding="utf-8") as handle:
        handle.write("not json")
    assert R.take() is None and not os.path.exists(R.MARKER)


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
