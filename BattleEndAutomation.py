"""
Battle-end auto-export for Pokemon TCG Live (v2.4 rework).

Goal: every finished battle ends up on the clipboard as a battle log, either
because the user exported it or because we clicked BATTLE LOG -> export for
them. The clipboard monitor treats both the same way, so this module only
has to (a) notice the end-of-battle screen quickly, (b) click the two buttons
safely, and (c) never fight the user.

State machine (one daemon thread, runs only while the game is running):

  IDLE/IN-BATTLE   HUD visible        -> poll HUD every 1.5 s (3 tiny patches)
  HOT              HUD lost < 3 min   -> look for BATTLE LOG every 0.25 s
  COLD             otherwise          -> look for BATTLE LOG every 1.5 s
                                         (catches arenas where the HUD check fails)
  BATTLE LOG template hit >= 0.93 -> cover Continue at once, then OCR
                                         (a look-alike that fails OCR drops the cover)
  BATTLE LOG seen (template + OCR "BATTLE LOG") ->
     * a battle log hit the clipboard in the last 25 s?  -> user did it, done
     * wait (<=20 s) for the game to be the foreground window (never click
       into another app)
     * show ONE Continue blocker, click BATTLE LOG, wait for the export icon,
       click export, wait for the monitor to confirm the clipboard capture,
       retry export at most twice, close the blocker
  DISARMED         after an end screen is handled, nothing is clicked again
                   until a new battle HUD is seen, or the BATTLE LOG button
                   has been absent for 60 s (covers arenas where the HUD
                   check fails). The same end screen is never processed twice.

All decisions are logged to Logs/autoclicker.log.
"""

import threading
import time

import numpy as np

import ocr_debug
from AutoClicker import AutoClicker
from BattleState import check_hud
from game_window import GameWindowCache, is_foreground, is_game_process_running

BATTLE_LOG = "battle_log"
EXPORT = "battle_log_export"


def reads_battle_log(gray_crop):
    """OCR the matched BATTLE LOG box; True only if it really says BATTLE LOG.

    Runs only on template hits (a few times per battle), ~50-150 ms each.
    """
    import re
    import cv2
    try:
        import pytesseract
        from RankDetector import _find_tesseract
        pytesseract.pytesseract.tesseract_cmd = _find_tesseract()
        # Tesseract reads this button reliably when the box is ~100-140 px
        # tall (tuned on the real template at 0.5x-1.4x window scales).
        for target, binarize in ((100, True), (100, False), (140, False)):
            f = target / float(max(1, gray_crop.shape[0]))
            img = 255 - cv2.resize(gray_crop, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
            if binarize:
                img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            img = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_REPLICATE)
            letters = re.sub(r"[^A-Z]", "", pytesseract.image_to_string(img, config="--psm 7").upper())
            if "BATTLE" in letters and "LOG" in letters:
                return True
    except Exception:
        return False
    return False

HOT_WINDOW_S = 180
HOT_POLL_S = 0.1
COLD_POLL_S = 1.5
HUD_POLL_S = 0.5
USER_EXPORT_GRACE_S = 25
FOREGROUND_WAIT_S = 20
EXPORT_SEARCH_S = 6.0
CAPTURE_CONFIRM_S = 2.5
EXPORT_RETRIES = 2
REARM_ABSENT_S = 60
# A real BATTLE LOG button scores 0.97-1.00; in-battle look-alikes 0.83-0.86.
# At this score Continue is covered before the OCR check (0.1-0.5 s, longer on
# slow PCs), so a quick click on Continue can't beat the export.
EARLY_COVER_SCORE = 0.93
PREWARM_EVERY_S = 30


class BattleEndAutomation(threading.Thread):
    def __init__(self, log_fn, launch_blocker, close_blocker, enabled_fn=lambda: True,
                 prewarm_blocker=lambda: None, wait_blocker=lambda proc: None):
        super().__init__(daemon=True, name="BattleEndAutomation")
        self.log = log_fn
        self.launch_blocker = launch_blocker
        self.close_blocker = close_blocker
        self.prewarm_blocker = prewarm_blocker
        self.wait_blocker = wait_blocker
        self.enabled_fn = enabled_fn
        self.clicker = AutoClicker()
        self.window = GameWindowCache(refresh_s=5.0)
        self._stop = threading.Event()
        self._capture_lock = threading.Lock()
        self._last_capture = 0.0
        self._capture_event = threading.Event()
        self._last_rejected_logged = None
        self._cover = None   # blocker shown early, before the OCR check
        self._can_cover = False
        self._cover_hwnd = None
        self.recorder = ocr_debug.EndScreenRecorder(log_fn)
        self.ready = self.clicker.load_template(BATTLE_LOG) and self.clicker.load_template(EXPORT)

    # ── called from the clipboard monitor ──────────────────────────────
    def notify_log_captured(self):
        """A battle log just landed on the clipboard (user or us)."""
        with self._capture_lock:
            self._last_capture = time.time()
        self._capture_event.set()

    def _captured_since(self, since):
        with self._capture_lock:
            return self._last_capture >= since

    def stop(self):
        self._stop.set()

    # ── capture helpers ────────────────────────────────────────────────
    @staticmethod
    def _bottom_half(rect):
        return {
            "left": rect["left"],
            "top": rect["top"] + rect["height"] // 2,
            "width": rect["width"],
            "height": rect["height"] - rect["height"] // 2,
        }

    def _grab(self, sct, name, rect, region):
        """The region as a frame; when the matcher will only read the
        button's remembered spot, only that spot is captured (the rest of
        the reused buffer is never read)."""
        box = self.clicker.next_search_box(name, rect["height"], region["width"], region["height"])
        if box is None:
            self._searched = region
            return np.asarray(sct.grab(region))
        x0, y0, x1, y1 = box
        self._searched = {"left": region["left"] + x0, "top": region["top"] + y0,
                          "width": x1 - x0, "height": y1 - y0}
        shape = (region["height"], region["width"], 4)
        if getattr(self, "_buffer", None) is None or self._buffer.shape != shape:
            self._buffer = np.zeros(shape, np.uint8)
        self._buffer[y0:y1, x0:x1] = np.asarray(sct.grab(
            {"left": region["left"] + x0, "top": region["top"] + y0, "width": x1 - x0, "height": y1 - y0}))
        return self._buffer

    def _find(self, sct, name, rect, region=None, verify=None):
        region = region or rect
        frame = self._grab(sct, name, rect, region)
        hit = self.clicker.find_in_frame(name, frame, (region["left"], region["top"]), rect["height"],
                                         verify=verify)
        if ocr_debug.enabled():
            label = "BATTLE LOG" if name == BATTLE_LOG else "Export"
            ocr_debug.report(f"{label} search", self._searched, hit=bool(hit),
                             score=self.clicker.last_score.get(name))
        return hit

    def _verify_battle_log(self, crop):
        # find_in_frame sets last_score before calling verify.
        if (self._can_cover and self._cover is None
                and self.clicker.last_score.get(BATTLE_LOG, 0) >= EARLY_COVER_SCORE
                and is_foreground(self._cover_hwnd)):
            self._cover = self.launch_blocker(wait_s=0)
        ok = reads_battle_log(crop)
        if not ok:
            self._drop_cover()
        return ok

    def _drop_cover(self):
        if self._cover is not None:
            self.close_blocker(self._cover)
            self._cover = None
            self.prewarm_blocker()

    def _battle_log_visible(self, sct, rect, cover_hwnd=None):
        """cover_hwnd: show the blocker on a strong template hit, before OCR."""
        self._can_cover, self._cover_hwnd = bool(cover_hwnd), cover_hwnd
        try:
            hit = self._find(sct, BATTLE_LOG, rect, self._bottom_half(rect), verify=self._verify_battle_log)
        finally:
            self._can_cover = False
        rejected = self.clicker.last_rejected.pop(BATTLE_LOG, None)
        if rejected and rejected != self._last_rejected_logged:
            self._last_rejected_logged = rejected
            self.log(f"Ignored BATTLE LOG look-alike at ({rejected[1]},{rejected[2]}) "
                     f"(score {rejected[0]:.2f}, text check failed).")
        return hit

    # ── main loop ──────────────────────────────────────────────────────
    def run(self):
        if not self.ready:
            self.log("Auto-export disabled: button templates missing. Run 'python SetupAutoClicker.py' to capture them.")
            return
        import mss
        self.log("Auto-export watcher started.")
        last_hud = 0.0
        in_battle = False
        streak = 0
        armed = True
        absent_since = time.time()
        last_prewarm = 0.0
        with mss.mss() as sct:
            while not self._stop.is_set():
                try:
                    if not self.enabled_fn():
                        time.sleep(5)
                        continue
                    hwnd = self.window.hwnd()
                    rect = self.window.rect() if hwnd else None
                    if not rect:
                        in_battle, streak = False, 0
                        time.sleep(3 if is_game_process_running() else 10)
                        continue

                    hud, _score, details = check_hud(rect, sct)
                    now = time.time()
                    if now - last_prewarm >= PREWARM_EVERY_S:
                        # Keep a hidden blocker loaded while the game is open,
                        # not only once the HUD gear is seen: arenas where the
                        # gear check fails would otherwise need a 1-2 s cold start.
                        self.prewarm_blocker()
                        last_prewarm = now
                    if hud:
                        if not in_battle:
                            self.log(f"Battle HUD detected ({details[0]}).")
                            try:
                                from deck_confirm import mark_battle_started
                                mark_battle_started()
                            except Exception:
                                pass
                            # Load the Continue blocker now (hidden) so it can
                            # cover Continue the instant the end screen shows.
                            self.prewarm_blocker()
                        in_battle, last_hud, armed = True, now, True
                        self.recorder.hud_back()
                    elif in_battle:
                        in_battle = False
                        self.log("Battle HUD gone - watching for the end screen.")
                        if ocr_debug.enabled():
                            self.recorder.start()
                    self.recorder.tick(sct, rect)

                    # Searched even while the HUD is visible (the in-battle gear
                    # may still be showing on the end screen); OCR verification
                    # makes in-battle look-alikes harmless.
                    hit = self._battle_log_visible(sct, rect, cover_hwnd=hwnd if armed else None)
                    if not hit:
                        streak = 0
                        if not armed and now - absent_since >= REARM_ABSENT_S:
                            armed = True
                    else:
                        absent_since = now
                        streak += 1
                    # One OCR-verified frame is proof enough (no second frame:
                    # every 0.25 s counts before the user can press Continue).
                    if armed and streak >= 1:
                        self.recorder.end_screen(sct, rect)
                        self._handle_end_screen(hwnd, sct, rect, hit, last_hud)
                        armed, streak, last_hud = False, 0, 0.0
                        absent_since = time.time()
                        continue
                    if in_battle and streak == 0:
                        time.sleep(HUD_POLL_S)
                        continue
                    hot = (now - last_hud) < HOT_WINDOW_S or streak > 0
                    time.sleep(HOT_POLL_S if (hot and armed) else COLD_POLL_S)
                except Exception as exc:  # never let the thread die
                    self.log(f"Auto-export loop error: {exc}")
                    time.sleep(3)

    # ── one end-of-battle screen ───────────────────────────────────────
    def _handle_end_screen(self, hwnd, sct, rect, hit, last_hud=0.0):
        seen_at = time.time()
        self.log(f"BATTLE LOG button visible (score {hit[2]:.2f}).")

        # Did the user already export THIS battle? "This battle" = since the
        # in-battle HUD was last seen, or the last 25 s if the HUD was never
        # detected (unusual arena themes).
        battle_ended = last_hud if last_hud else seen_at - USER_EXPORT_GRACE_S
        if self._captured_since(battle_ended):
            self.log("Battle log already on clipboard - nothing to click.")
            self._drop_cover()
            return

        # The blocker is always-on-top, so only show it while the game is the
        # focused window (it used to sit over other apps while the game was in
        # the background). Never click into another app either.
        deadline = time.time() + FOREGROUND_WAIT_S
        while not is_foreground(hwnd):
            if time.time() > deadline or self._stop.is_set():
                self.log("Game not in foreground - skipped auto-export (export manually).")
                self._drop_cover()
                return
            if self._captured_since(seen_at):
                self.log("User exported while game was unfocused.")
                self._drop_cover()
                return
            time.sleep(0.1)
        # Cover Continue first, before anything else can take time (usually
        # it already is: the cover went up on the template hit, before OCR).
        blocker, self._cover = self._cover, None
        if blocker is not None:
            self.log("Continue covered on the template hit, before the text check.")
            self.wait_blocker(blocker)
        else:
            blocker = self.launch_blocker()
        try:
            exported = self._click_sequence(sct, hwnd, rect, seen_at)
            self.log("Auto-export complete." if exported else "Auto-export did not confirm a clipboard capture.")
        finally:
            self.close_blocker(blocker)
            # Reload a hidden standby blocker straight away, so a re-detected
            # end screen (or the next battle) never needs a cold start.
            self.prewarm_blocker()

    def _click_sequence(self, sct, hwnd, rect, seen_at):
        hit = self._battle_log_visible(sct, rect)
        if not hit:
            self.log("BATTLE LOG button vanished before the click (user pressed Continue?).")
            return self._captured_since(seen_at)
        self._capture_event.clear()
        AutoClicker.physical_click(hit[0], hit[1])
        self.log(f"Clicked BATTLE LOG at ({hit[0]},{hit[1]}).")

        export = None
        reclicked = False
        deadline = time.time() + EXPORT_SEARCH_S
        while time.time() < deadline and not self._stop.is_set():
            if self._captured_since(seen_at):
                return True  # user beat us to it
            export = self._find(sct, EXPORT, rect)
            if export:
                break
            # Popup didn't open (click eaten by an animation)? Re-click once.
            if not reclicked and time.time() > deadline - EXPORT_SEARCH_S + 1.5:
                again = self._battle_log_visible(sct, rect)
                if again and is_foreground(hwnd):
                    AutoClicker.physical_click(again[0], again[1])
                    self.log("Re-clicked BATTLE LOG (popup did not open).")
                reclicked = True
            time.sleep(0.12)
        if not export:
            self.log(f"Export button not found within {EXPORT_SEARCH_S:.0f}s "
                     f"(best score {self.clicker.last_score.get(EXPORT, 0):.2f}).")
            return self._captured_since(seen_at)

        for attempt in range(EXPORT_RETRIES + 1):
            if not is_foreground(hwnd):
                self.log("Game lost focus - stopped clicking.")
                break
            AutoClicker.physical_click(export[0], export[1])
            self.log(f"Clicked export at ({export[0]},{export[1]})" + (f" (retry {attempt})" if attempt else "") + ".")
            if self._capture_event.wait(CAPTURE_CONFIRM_S) or self._captured_since(seen_at):
                return True
            again = self._find(sct, EXPORT, rect)
            if not again:
                break
            export = again
        return self._captured_since(seen_at)
