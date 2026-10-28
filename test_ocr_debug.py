"""OCR Bounding Box Debug: box reports, end-screen recording and draggable
boxes (run: python test_ocr_debug.py). Works in a temp folder, offscreen Qt."""
import json
import os
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import ocr_debug as D

TMP = tempfile.mkdtemp(prefix="ocr_debug_test_")
D.LOG_DIR = TMP
D.END_SCREEN_DIR = os.path.join(TMP, "end_screens")
D.REGIONS_FILE = os.path.join(TMP, "screen_regions.json")
GAME = {"left": 100, "top": 50, "width": 1000, "height": 500}


def debug(on):
    D._state.update(on=on, checked=time.time() + 3600)


class Screen:
    def grab(self, rect):
        return np.full((rect["height"], rect["width"], 4), 90, np.uint8)


def test_off_writes_nothing():
    debug(False)
    D.report("rank", {"left": 1, "top": 2, "width": 3, "height": 4})
    assert not os.path.exists(D.debug_file())


def test_reports_reach_the_overlay():
    debug(True)
    D._state["written"] = 0
    D.report("HUD gear", {"left": 10, "top": 20, "width": 30, "height": 40}, hit=True, score=0.987)
    D._state["written"] = 0
    D.report("rank", {"left": 5, "top": 6, "width": 7, "height": 8}, text="  1489\n")
    boxes = D.read_all()
    assert boxes["HUD gear"]["hit"] is True and boxes["HUD gear"]["score"] == 0.99
    assert boxes["rank"]["text"] == "1489"
    # a later capture of the same box keeps the reading
    D._state["written"] = 0
    D.report("rank", {"left": 5, "top": 6, "width": 7, "height": 8})
    assert D.read_all()["rank"]["text"] == "1489"
    assert D.read_all(now=time.time() + D.KEEP_S + 1) == {}  # stale boxes fade out


def test_recording_without_end_screen_is_deleted():
    rec = D.EndScreenRecorder()
    rec.start()
    rec.tick(Screen(), GAME)
    folder = rec.dir
    assert os.listdir(folder)
    rec.hud_back()  # only a deck search
    assert not os.path.exists(folder) and rec.dir is None


def test_end_screen_recording_is_kept_and_pruned():
    for i in range(D.EndScreenRecorder.KEEP + 2):
        os.makedirs(os.path.join(D.END_SCREEN_DIR, f"2026-01-0{i + 1}_00-00-00"))
    rec = D.EndScreenRecorder()
    rec.start()
    rec.tick(Screen(), GAME)
    rec.end_screen(Screen(), GAME)
    folder = rec.dir
    rec.until = 0
    rec.tick(Screen(), GAME)
    files = os.listdir(folder)
    assert "end_screen_full.png" in files and any(f.endswith(".jpg") for f in files)
    assert len(os.listdir(D.END_SCREEN_DIR)) == D.EndScreenRecorder.KEEP


def test_drag_box_corners_and_move():
    from debug_overlay import MIN_SIDE, drag_box
    box = {"left": 100, "top": 100, "width": 50, "height": 20}
    assert drag_box(box, "br", 10, 5) == {"left": 100, "top": 100, "width": 60, "height": 25}
    assert drag_box(box, "tl", -10, -5) == {"left": 90, "top": 95, "width": 60, "height": 25}
    assert drag_box(box, "move", 7, 3) == {"left": 107, "top": 103, "width": 50, "height": 20}
    assert drag_box(box, "tr", -500, 0)["width"] == MIN_SIDE


def test_saved_box_round_trips_as_window_fractions():
    with open(D.REGIONS_FILE, "w") as f:
        json.dump({"rank": {"relative": True, "percent_x": 0.5, "percent_y": 0.5,
                            "percent_width": 0.1, "percent_height": 0.05}}, f)
    box = D.region_box(D.load_regions()["rank"], GAME)
    assert box == {"left": 600, "top": 300, "width": 100, "height": 25}
    moved = dict(box, left=650, width=120)
    assert D.save_region("rank", moved, GAME)
    assert D.region_box(D.load_regions()["rank"], GAME) == moved
    assert os.path.exists(D.REGIONS_FILE.replace(".json", ".before_debug.json"))
    assert not D.save_region("not_a_region", moved, GAME)


def test_overlay_paints_and_edits_offscreen():
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication
    import debug_overlay as O
    app = QApplication.instance() or QApplication([])
    debug(True)
    w = O.DebugOverlay()
    w.timer.stop()
    w.game = GAME
    w.resize(GAME["width"], GAME["height"])
    w.boxes = D.read_all()
    w.editing = True
    w._load_edit_boxes()
    assert "rank" in w.edit_boxes
    w.grab()  # paints without errors
    rect = w._to_view(w.edit_boxes["rank"])
    assert w._grab_at(rect.bottomRight()) == ("rank", "br")
    assert w._grab_at(rect.center()) == ("rank", "move")
    assert w._grab_at(QPointF(2, 400)) is None  # empty space goes to the game
    w.close()


if __name__ == "__main__":
    failures = 0
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                try:
                    fn()
                    print(f"PASS {name}")
                except Exception as exc:
                    failures += 1
                    print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failures else 0)
