"""Menu OCR reads the game window's own pixels (right even when covered),
and falls back to the screen when Windows can't give them."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402

import game_window  # noqa: E402
import RankDetector as R  # noqa: E402

RECT = {"hwnd": 7, "title": "Pokemon TCG Live", "left": 100, "top": 50, "width": 400, "height": 300}


def _detector():
    d = R.RankDetector()
    d.regions = {"box": {"relative": True, "percent_x": 0.5, "percent_y": 0.5,
                         "percent_width": 0.1, "percent_height": 0.1}}
    d.find_game_window = lambda: (setattr(d, "game_window", dict(RECT)) or d.game_window)
    return d


def test_crops_the_window_capture():
    shot = Image.new("RGB", (400, 300), (0, 0, 0))
    shot.paste((200, 10, 10), (200, 150, 240, 180))   # the region: x 200-240, y 150-180 in the window
    with mock.patch.object(game_window, "capture_window", return_value=(shot, dict(RECT))), \
            mock.patch.object(R.mss, "mss", side_effect=AssertionError("screen grab used")):
        img = _detector().capture_region("box")
    assert img.size == (40, 30), img.size
    assert img.getpixel((0, 0)) == (200, 10, 10) and img.getpixel((39, 29)) == (200, 10, 10)


def test_falls_back_to_the_screen():
    class Grab:
        size = (40, 30)
        bgra = bytes([1, 2, 3, 0]) * (40 * 30)

    class Sct:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def grab(self, monitor):
            assert monitor == {"top": 200, "left": 300, "width": 40, "height": 30}, monitor
            return Grab()

    with mock.patch.object(game_window, "capture_window", return_value=(None, None)), \
            mock.patch.object(R.mss, "mss", return_value=Sct()):
        img = _detector().capture_region("box")
    assert img.getpixel((0, 0)) == (3, 2, 1)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
