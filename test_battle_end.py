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
    def __init__(self, score, text_ok=True, foreground=True, on_screen=False):
        self.events = []
        B.is_foreground = lambda hwnd: foreground
        B.can_cover_continue = lambda hwnd, rect=None: foreground or on_screen
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
    # the next standby is loaded before this cover closes
    assert f.events == [("show", 0), "ocr", "prewarm", ("close", "blocker")]
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
        B.can_cover_continue = lambda hwnd, rect=None: self.focus
        import contextlib
        self.auto._hold_input = lambda: contextlib.nullcontext()
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


def _image_fake(score, text_ok, crop):
    """Fake whose matcher hands verify() a real gray crop (nothing saved to Logs)."""
    import numpy as np
    f = Fake(score, text_ok=text_ok)
    f.auto._lookalikes_saved = B.LOOKALIKE_SAVE_MAX

    def find(sct, name, rect, region=None, verify=None):
        f.auto.clicker.last_score[name] = score
        if verify is not None and not verify(np.asarray(f.crop, np.uint8)):
            return None
        return (100, 200, score)
    f.auto._find = find
    f.crop = crop
    return f


def test_repeated_look_alike_skips_ocr_and_cover():
    import numpy as np
    crop = np.tile(np.arange(120, dtype=np.uint8), (40, 1))
    f = _image_fake(0.99, False, crop)
    assert not f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    assert f.events.count("ocr") == 1 and f.events.count(("show", 0)) == 1
    f.events.clear()
    f.crop = crop + 1  # same picture, a hair brighter
    assert not f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    assert "ocr" not in f.events and ("show", 0) not in f.events


def test_a_different_crop_is_still_read():
    import numpy as np
    crop = np.tile(np.arange(120, dtype=np.uint8), (40, 1))
    f = _image_fake(0.99, False, crop)
    f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    f.events.clear()
    f.text_ok = True
    f.crop = 255 - crop  # the real button: different pixels
    assert f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    assert "ocr" in f.events


def _hud_frame(height, gear_fraction, centre):
    """A dark game frame with the gear template pasted at `centre` (fractions)."""
    import cv2
    import numpy as np
    import BattleState
    width = height * 16 // 9
    frame = np.full((height, width, 3), 40, np.uint8)
    tpl = cv2.imread(BattleState.GEAR_TEMPLATE)
    n = int(round(height * gear_fraction))
    gear = cv2.resize(tpl, (n, n), interpolation=cv2.INTER_AREA)
    x, y = int(width * centre[0]) - n // 2, int(height * centre[1]) - n // 2
    frame[y:y + n, x:x + n] = gear
    return frame


class _FrameSct:
    def __init__(self, frame):
        self.frame = frame

    def grab(self, box):
        import cv2
        x, y, w, h = box["left"], box["top"], box["width"], box["height"]
        return cv2.cvtColor(self.frame[y:y + h, x:x + w], cv2.COLOR_BGR2BGRA)


def test_hud_gear_found_at_old_and_new_size():
    import BattleState
    for height in (720, 1136, 1440):
        rect = {"left": 0, "top": 0, "width": height * 16 // 9, "height": height}
        new = _hud_frame(height, 16 / 720.0, (0.988, 0.021))   # since the Nov 2026 update
        old = _hud_frame(height, 36 / 1136.0, (0.969, 0.086))  # before it
        assert BattleState.check_hud(rect, _FrameSct(new))[0], height
        assert BattleState.check_hud(rect, _FrameSct(old))[0], height
        blank = new.copy()
        blank[:] = 40
        assert not BattleState.check_hud(rect, _FrameSct(blank))[0], height


def test_white_flash_covers_continue_and_export_reuses_it():
    f = Fake(0.98)
    f.auto._start_white_stage(1)
    assert f.events[0] == ("show", 0) and f.auto._cover == "blocker"
    hit = f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    assert f.events.count(("show", 0)) == 1   # no second cover on the template hit
    f.auto._click_sequence = lambda *a: True
    f.auto._handle_end_screen(1, None, RECT, hit)
    assert any("since the white flash" in str(e) for e in f.events)
    assert ("close", "blocker") in f.events and f.auto._white_since is None


def test_look_alike_keeps_the_white_flash_cover():
    f = Fake(0.99, text_ok=False)
    f.auto._start_white_stage(1)
    assert not f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    assert ("close", "blocker") not in f.events and f.auto._cover == "blocker"


def test_white_stage_ends_and_uncovers():
    f = Fake(0.5)
    f.auto._start_white_stage(1)
    f.auto._end_white_stage("No end screen")
    assert ("close", "blocker") in f.events and f.auto._cover is None
    assert f.auto._white_since is None


def test_white_flash_unfocused_does_not_cover():
    f = Fake(0.5, foreground=False)
    f.auto._start_white_stage(1)
    assert ("show", 0) not in f.events and f.auto._white_since is not None


def test_white_flash_covers_when_the_game_shows_but_is_unfocused():
    # Clicking the game to focus it would also press Continue.
    f = Fake(0.5, foreground=False, on_screen=True)
    f.auto._start_white_stage(1, RECT)
    assert f.events[0] == ("show", 0) and f.auto._cover == "blocker"


def test_end_screen_unfocused_is_covered_before_waiting_for_focus():
    f = Fake(0.98, foreground=False, on_screen=True)
    B.FOREGROUND_WAIT_S = 0.2
    f.auto._handle_end_screen(1, None, RECT, (100, 200, 0.98))
    assert f.events.index(("show", 0)) < f.events.index(("close", "blocker"))
    assert any("not in foreground" in str(e) for e in f.events)
    B.FOREGROUND_WAIT_S = 20


def test_stage_signals_on_synthetic_frames():
    import numpy as np
    import BattleState
    for height in (720, 1440):
        width = height * 16 // 9
        rect = {"left": 0, "top": 0, "width": width, "height": height}
        board = np.full((height, width, 3), 40, np.uint8)
        u = height / 720.0
        # prize counters: red box above blue box at the right edge (BGR)
        x0, x1 = int(width - 34 * u), int(width - 4 * u)
        board[int(275 * u):int(312 * u), x0:x1] = (40, 40, 200)
        board[int(325 * u):int(362 * u), x0:x1] = (200, 90, 40)
        assert BattleState.battle_signals(rect, _FrameSct(board))["counters"], height
        assert not BattleState.white_flash(rect, _FrameSct(board)), height
        white = np.full_like(board, 255)
        assert BattleState.white_flash(rect, _FrameSct(white)), height
        sig = BattleState.battle_signals(rect, _FrameSct(white))
        assert not sig["counters"] and not sig["emotes"], height


def test_look_alike_memory_expires():
    import numpy as np
    crop = np.full((40, 120), 90, np.uint8)
    f = _image_fake(0.99, False, crop)
    f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    f.auto._rejected_sigs = [(s, t - B.REJECT_MEMORY_S - 1) for s, t in f.auto._rejected_sigs]
    f.events.clear()
    f.auto._battle_log_visible(None, RECT, cover_hwnd=1)
    assert "ocr" in f.events


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
