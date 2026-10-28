"""BattleEndAutomation: Continue is covered on a strong BATTLE LOG template
hit, before the OCR check (run: python test_battle_end.py). No screen, no
clicks: the matcher, OCR and blocker are fakes."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import BattleEndAutomation as B

RECT = {"left": 0, "top": 0, "width": 1942, "height": 1136}


class Fake:
    def __init__(self, score, text_ok=True, foreground=True):
        self.events = []
        B.is_foreground = lambda hwnd: foreground
        B.reads_battle_log = self._ocr
        self.text_ok = text_ok
        self.auto = B.BattleEndAutomation(
            self.events.append,
            launch_blocker=lambda wait_s=4.0: self.events.append(("show", wait_s)) or "blocker",
            close_blocker=lambda proc: self.events.append(("close", proc)),
            prewarm_blocker=lambda: self.events.append("prewarm"),
            wait_blocker=lambda proc: self.events.append(("wait", proc)),
        )

        def find(sct, name, rect, region=None, verify=None):
            self.auto.clicker.last_score[name] = score
            if score < 0.8:
                return None
            if verify is not None and not verify("crop"):
                return None
            return (100, 200, score)
        self.auto._find = find

    def _ocr(self, crop):
        self.events.append("ocr")
        return self.text_ok


def test_strong_hit_covers_before_ocr():
    f = Fake(0.98)
    assert f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    assert f.events[:2] == [("show", 0), "ocr"]
    assert f.auto._cover == "blocker"


def test_look_alike_drops_the_cover():
    f = Fake(0.95, text_ok=False)
    assert not f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    assert f.events == [("show", 0), "ocr", ("close", "blocker"), "prewarm"]
    assert f.auto._cover is None


def test_weak_hit_waits_for_ocr():
    f = Fake(0.86)
    assert f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    assert f.events == ["ocr"]


def test_disarmed_or_unfocused_never_covers():
    f = Fake(0.99)
    f.auto._battle_log_visible(None, RECT, cover_hwnd=None)  # end screen already handled
    assert ("show", 0) not in f.events
    g = Fake(0.99, foreground=False)
    g.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    assert ("show", 0) not in g.events


def test_export_reuses_the_early_cover():
    f = Fake(0.98)
    hit = f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    f.auto._click_sequence = lambda *a: True
    f.auto._handle_end_screen(1, None, RECT, hit)
    shows = [e for e in f.events if isinstance(e, tuple) and e[0] == "show"]
    assert shows == [("show", 0)]  # no second blocker
    assert ("wait", "blocker") in f.events and ("close", "blocker") in f.events


def test_user_already_exported_drops_the_cover():
    f = Fake(0.98)
    hit = f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    f.auto.notify_log_captured()
    f.auto._handle_end_screen(1, None, RECT, hit, last_hud=1.0)
    assert ("close", "blocker") in f.events and f.auto._cover is None


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
