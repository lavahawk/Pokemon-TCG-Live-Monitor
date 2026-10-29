"""BattleEndAutomation: Continue is covered on a strong BATTLE LOG template
hit, before the OCR check (run: python test_battle_end.py). No screen, no
clicks: the matcher, OCR and blocker are fakes."""
import os
import sys
import time

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


def test_click_step_does_not_re_read_the_text():
    f = Fake(0.98)
    f.auto._find_calls = []
    find = f.auto._find
    f.auto._find = lambda sct, name, rect, region=None, verify=None: (
        f.auto._find_calls.append(verify) or find(sct, name, rect, region, verify))
    f.text_ok = False  # the button is mid-animation: OCR would fail now
    assert f.auto._button_still_there(None, RECT)
    assert f.auto._find_calls == [None] and "ocr" not in f.events


class EndScreen:
    """A scripted end screen for _click_sequence: clicking BATTLE LOG opens
    the popup, clicking export copies the log (unless `swallow` says the
    click was lost); `script` runs after each click, like the user acting."""

    def __init__(self, script=None, swallow=0):
        self.popup, self.end, self.focus = False, True, True
        self.clicks, self.script, self.swallow = [], script or (lambda s: None), swallow
        f = Fake(0.98)
        self.events, self.auto = f.events, f.auto
        B.SEQUENCE_MAX_S, B.REOPEN_EVERY_S, B.CAPTURE_CONFIRM_S, B.GONE_S = 3, 0.05, 0.05, 0.3
        B.is_foreground = lambda hwnd: self.focus
        self.auto._wait_for_still_mouse = lambda: None
        self.auto._find = lambda sct, name, rect, region=None, verify=None: (
            (900, 100, 1.0) if (name == B.EXPORT and self.popup and self.end) else None)
        self.auto._button_still_there = lambda sct, rect: (
            (500, 800, 1.0) if (self.end and not self.popup) else None)
        B.AutoClicker.physical_click = staticmethod(self.click)

    def click(self, x, y):
        name = "export" if (x, y) == (900, 100) else "battle log"
        self.clicks.append(name)
        if name == "battle log":
            self.popup = True
        elif self.swallow:
            self.swallow -= 1
        else:
            self.auto.notify_log_captured()
        self.script(self)

    def run(self):
        return self.auto._click_sequence(None, 1, RECT, time.time())


def test_export_retries_when_the_user_closes_the_popup():
    def user(screen):
        if screen.clicks == ["battle log"]:
            screen.popup = False  # the user's click closed the popup
    s = EndScreen(user)
    assert s.run()
    assert s.clicks == ["battle log", "battle log", "export"]


def test_export_waits_for_focus_instead_of_giving_up():
    def user(screen):
        if screen.clicks == ["battle log"]:
            screen.focus = False  # clicked another window
            import threading
            threading.Timer(0.4, lambda: setattr(screen, "focus", True)).start()
    s = EndScreen(user)
    assert s.run()
    assert s.clicks == ["battle log", "export"]
    assert any("lost focus" in str(e) for e in s.events)


def test_swallowed_export_clicks_are_retried():
    s = EndScreen(swallow=2)
    assert s.run()
    assert s.clicks == ["battle log", "export", "export", "export"]


def test_continue_pressed_ends_the_sequence():
    def user(screen):
        screen.end = False  # Continue pressed right after the first click
    s = EndScreen(user)
    assert not s.run()
    assert s.clicks == ["battle log"]
    assert any("End screen gone" in str(e) for e in s.events)


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
