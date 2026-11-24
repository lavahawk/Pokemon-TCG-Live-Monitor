"""
Battle-end auto-export for Pokemon TCG Live (v2.4 rework).

Goal: every finished battle ends up on the clipboard as a battle log, either
because the user exported it or because we clicked BATTLE LOG -> export for
them. The clipboard monitor treats both the same way, so this module only
has to (a) notice the end-of-battle screen quickly, (b) click the two buttons
safely, and (c) never fight the user.

State machine (one daemon thread, runs only while the game is running):

  IN-BATTLE        HUD visible        -> poll HUD every 0.5 s (gear top right,
                                         emote buttons left, prize counters right)
  HOT              HUD lost < 3 min   -> look for the white flash and BATTLE LOG
                                         every 0.15 s
  WHITE            white flash seen   -> cover Continue at once, look for BATTLE
                                         LOG every 0.03 s (uncover after 12 s or
                                         if the HUD comes back)
  COLD             otherwise          -> look for BATTLE LOG every 1.5 s
                                         (catches arenas where the HUD check fails)
  BATTLE LOG template hit >= 0.93 -> cover Continue at once, then OCR
                                         (a look-alike that fails OCR drops the cover)
  BATTLE LOG seen (template + OCR "BATTLE LOG") ->
     * a battle log hit the clipboard in the last 25 s?  -> user did it, done
     * wait (<=20 s) for the game to be the foreground window (never click
       into another app)
     * show ONE Continue blocker, then until the log is on the clipboard
       (<=25 s): export icon showing -> click it; popup closed -> click
       BATTLE LOG again; game unfocused -> wait; mouse moving -> let it
       settle first. Stops early if the end screen is gone. Close the blocker
  CONCEDED?        HUD gone 4 s, no end screen, then the main menu (checked
                   every 2 s on its own thread, for up to 90 s): conceding
                   skips the end screen, so on_menu_without_end() asks
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
from BattleState import battle_signals, check_hud, white_flash
from game_window import GameWindowCache, can_cover_continue, is_foreground, is_game_process_running

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
# Staged end of a battle (Nov 2026 layout): in battle the HUD (gear, emote
# buttons, prize counters) is polled every HUD_POLL_S; once all of it is gone
# the white flash is looked for every HOT_POLL_S; on the flash Continue is
# covered at once and BATTLE LOG is looked for every WHITE_POLL_S.
HOT_POLL_S = 0.06          # was 0.15: a short white flash was missed on slow PCs
WHITE_POLL_S = 0.03
WHITE_STAGE_MAX_S = 12     # no end screen this long after the flash: uncover
COLD_POLL_S = 1.5
HUD_POLL_S = 0.5
# HUD seen without the gear (only the emote buttons or prize counters): those
# also match some end screens, so keep looking for BATTLE LOG quickly.
WEAK_HUD_POLL_S = 0.15
# During the white stage the HUD has to be back this long before Continue is
# uncovered: a one-frame false HUD on the end screen used to drop the cover
# just before BATTLE LOG showed, and the new cover needed a fresh blocker.
HUD_BACK_S = 1.0
USER_EXPORT_GRACE_S = 25
FOREGROUND_WAIT_S = 20
# The export keeps retrying until the log is on the clipboard: a click of
# the user's can close the BATTLE LOG popup or move focus mid-sequence.
SEQUENCE_MAX_S = 25        # under the blocker's 30 s failsafe
REOPEN_EVERY_S = 1.5       # popup closed: click BATTLE LOG again after this
CAPTURE_CONFIRM_S = 2.5    # after an export click, wait this long for the log
GONE_S = 2.0               # neither button for this long: the end screen is gone
# Each click holds the player's mouse and keyboard (and hides the cursor)
# for its ~0.4 s, the way the friend-request clicks do, instead of waiting
# for a moving mouse to rest (up to 1.5 s per click). Esc lets go.
HOLD_MAX_S = 3             # the hold always lets go after this long
BUTTON_HELD_WAIT_S = 1.5   # a held left button is let go first (mid-drag)
# Conceding goes from the battle straight to the main menu (no end screen).
MENU_WATCH_AFTER_S = 4     # HUD gone this long without an end screen: look for the menu
MENU_WATCH_S = 90
MENU_CHECK_EVERY_S = 2
REARM_ABSENT_S = 60
# A real BATTLE LOG button scores 0.97-1.00; in-battle look-alikes 0.83-0.86.
# At this score Continue is covered before the OCR check (0.1-0.5 s, longer on
# slow PCs), so a quick click on Continue can't beat the export.
EARLY_COVER_SCORE = 0.93
PREWARM_EVERY_S = 30
# A battle that ended without the HUD gear ever matching means the gear
# template is stale (a game update moved or redrew it, as in Nov 2026). The
# HOT/COLD choice then always picks COLD, so the end screen was found up to
# 1.5 s late; poll at this rate instead until the gear matches again.
HUDLESS_POLL_S = 0.15
# Look-alikes that failed the text check: an identical crop is rejected
# again without OCR (Tesseract gives the same answer on the same pixels) and
# without raising the Continue cover over a live battle.
REJECT_SIG_SIZE = (96, 32)
REJECT_SIG_MAX_DIFF = 1.5   # mean abs gray difference, 0-255
REJECT_MEMORY_S = 600
REJECT_MEMORY_MAX = 8
LOOKALIKE_SAVE_MAX = 20     # crops kept in Logs/battle_log_lookalikes


def _foreground_name():
    """Title and process of the window in front, for the log."""
    try:
        import psutil
        import win32gui
        import win32process
        fg = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(fg)
        proc = psutil.Process(pid)
        script = next((os_path for os_path in proc.cmdline() if os_path.endswith('.py')), '')
        return f"'{win32gui.GetWindowText(fg)}' {proc.name()} {script.split(chr(92))[-1]}".strip()
    except Exception:
        return "unknown"


def crop_signature(gray_crop):
    import cv2
    return cv2.resize(gray_crop, REJECT_SIG_SIZE, interpolation=cv2.INTER_AREA).astype(np.int16)


def same_crop(sig_a, sig_b):
    return float(np.abs(sig_a - sig_b).mean()) <= REJECT_SIG_MAX_DIFF


class BattleEndAutomation(threading.Thread):
    def __init__(self, log_fn, launch_blocker, close_blocker, enabled_fn=lambda: True,
                 prewarm_blocker=lambda: None, wait_blocker=lambda proc: None,
                 on_menu_without_end=lambda battle_started: None):
        super().__init__(daemon=True, name="BattleEndAutomation")
        self.log = log_fn
        self.launch_blocker = launch_blocker
        self.close_blocker = close_blocker
        self.prewarm_blocker = prewarm_blocker
        self.wait_blocker = wait_blocker
        self.on_menu_without_end = on_menu_without_end
        self._battle_since = None   # first HUD of the battle in progress
        self._last_hud_at = 0.0
        self._menu_watch = None
        self.enabled_fn = enabled_fn
        self.clicker = AutoClicker()
        self.window = GameWindowCache(refresh_s=5.0)
        self._stop = threading.Event()
        self._capture_lock = threading.Lock()
        self._last_capture = 0.0
        self._capture_event = threading.Event()
        self._escaped = threading.Event()   # Esc during a click: stop exporting
        self._last_rejected_logged = None
        self._cover = None   # blocker shown early, before the OCR check
        self._can_cover = False
        self._cover_hwnd = None
        self._rejected_sigs = []    # [(signature, time)] of look-alikes
        self._lookalikes_saved = 0
        self._hud_unreliable = False
        self._white_since = None    # white flash seen; Continue covered since then
        self._hud_back_since = None  # HUD seen again during the white stage
        self._hud_ever_seen = False  # until then the HUD templates are unproven
        self._cover_rect = None
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

    def _known_lookalike(self, sig):
        now = time.time()
        self._rejected_sigs = [(s, t) for s, t in self._rejected_sigs if now - t < REJECT_MEMORY_S]
        return any(same_crop(sig, s) for s, _t in self._rejected_sigs)

    def _remember_lookalike(self, sig, crop):
        self._rejected_sigs = (self._rejected_sigs + [(sig, time.time())])[-REJECT_MEMORY_MAX:]
        if self._lookalikes_saved >= LOOKALIKE_SAVE_MAX:
            return
        try:
            import os
            import cv2
            folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logs", "battle_log_lookalikes")
            os.makedirs(folder, exist_ok=True)
            score = self.clicker.last_score.get(BATTLE_LOG, 0)
            cv2.imwrite(os.path.join(folder, f"{time.strftime('%Y%m%d_%H%M%S')}_{score:.2f}.png"), crop)
            self._lookalikes_saved += 1
        except Exception:
            pass

    def _verify_battle_log(self, crop):
        try:
            sig = crop_signature(crop)
        except Exception:
            sig = None
        if sig is not None and self._known_lookalike(sig):
            return False
        # find_in_frame sets last_score before calling verify.
        if (self._can_cover and self._cover is None
                and self.clicker.last_score.get(BATTLE_LOG, 0) >= EARLY_COVER_SCORE
                and can_cover_continue(self._cover_hwnd, self._cover_rect)):
            self._cover = self.launch_blocker(wait_s=0)
        ok = reads_battle_log(crop)
        if not ok:
            if self._white_since is None:   # the flash's cover stays up
                self._drop_cover()
            if sig is not None:
                self._remember_lookalike(sig, crop)
        return ok

    def _start_white_stage(self, hwnd, rect=None):
        """The white flash before the end screen: cover Continue now, so
        the end screen can't be clicked away before BATTLE LOG is found.
        Also when another window has the focus but the game shows: the click
        that focuses the game would land on Continue."""
        self._white_since = time.time()
        self._hud_back_since = None
        if self._cover is None and can_cover_continue(hwnd, rect):
            self._cover = self.launch_blocker(wait_s=0)
            self.log("White flash - Continue covered, watching for BATTLE LOG.")
        else:
            self.log("White flash - watching for BATTLE LOG.")

    def _end_white_stage(self, message):
        self._white_since = None
        self.log(message)
        self._drop_cover()

    def _drop_cover(self):
        if self._cover is not None:
            # Load the next hidden blocker before closing this one, so a
            # cover needed right after (the end screen a moment later) is a
            # signal away, not a 1-2 s Qt start.
            self.prewarm_blocker()
            self.close_blocker(self._cover)
            self._cover = None

    def _battle_log_visible(self, sct, rect, cover_hwnd=None):
        """cover_hwnd: show the blocker on a strong template hit, before OCR."""
        self._can_cover, self._cover_hwnd, self._cover_rect = bool(cover_hwnd), cover_hwnd, rect
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
                        self._battle_since = None  # game closed: that battle is over
                        time.sleep(3 if is_game_process_running() else 10)
                        continue

                    gear, _score, details = check_hud(rect, sct)
                    if gear:
                        # The gear is proof on its own; the board checks
                        # (~10 ms) only run when it doesn't match.
                        hud = True
                    else:
                        signals = battle_signals(rect, sct)
                        hud = signals["emotes"] or signals["counters"]
                        details = [f"{details[0]} {signals['details']}"]
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
                        self._hud_ever_seen = True
                        if self._hud_unreliable:
                            self._hud_unreliable = False
                            self.log("Battle HUD gear matches again - normal end-screen polling.")
                        self._last_hud_at = now
                        if self._battle_since is None:
                            self._battle_since = now
                        if self._white_since is not None:
                            self._hud_back_since = self._hud_back_since or now
                            if now - self._hud_back_since >= HUD_BACK_S:
                                self._end_white_stage("Battle HUD back after a white frame - Continue uncovered.")
                        self.recorder.hud_back()
                    elif in_battle:
                        in_battle = False
                        self.log("Battle HUD gone - watching for the end screen.")
                        if ocr_debug.enabled():
                            self.recorder.start()
                    if not hud:
                        self._hud_back_since = None
                    self.recorder.tick(sct, rect)
                    if (not hud and armed and self._battle_since and self._menu_watch is None
                            and now - self._last_hud_at >= MENU_WATCH_AFTER_S):
                        self._menu_watch = threading.Thread(
                            target=self._watch_for_menu, args=(self._battle_since, self._last_hud_at),
                            daemon=True, name="ConcedeWatch")
                        self._menu_watch.start()

                    # Battle over (HUD gone, end screen not handled yet): the
                    # white flash comes right before the end screen.
                    if (not hud and armed and last_hud and self._white_since is None
                            and now - last_hud < HOT_WINDOW_S and white_flash(rect, sct)):
                        self._start_white_stage(hwnd, rect)
                    elif self._white_since is not None and now - self._white_since > WHITE_STAGE_MAX_S:
                        self._end_white_stage(f"No end screen {WHITE_STAGE_MAX_S}s after the white "
                                              "flash - Continue uncovered.")

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
                        if not last_hud and not self._hud_unreliable:
                            self._hud_unreliable = True
                            self.log("Battle ended without the battle HUD matching (gear, emote buttons, "
                                     "prize counters; templates stale after a game update?) - polling for "
                                     f"the end screen every {HUDLESS_POLL_S}s. The HUD templates in "
                                     "button_templates need recapturing.")
                        self._handle_end_screen(hwnd, sct, rect, hit, last_hud)
                        armed, streak, last_hud = False, 0, 0.0
                        self._battle_since = None  # this battle had its end screen
                        absent_since = time.time()
                        continue
                    if self._white_since is not None:
                        time.sleep(WHITE_POLL_S)
                        continue
                    if in_battle and streak == 0:
                        time.sleep(HUD_POLL_S if gear else WEAK_HUD_POLL_S)
                        continue
                    hot = (now - last_hud) < HOT_WINDOW_S or streak > 0
                    if hot and armed:
                        time.sleep(HOT_POLL_S)
                    elif armed and (self._hud_unreliable or not self._hud_ever_seen) and is_foreground(hwnd):
                        # No working HUD check to say a battle is on (a new
                        # PC, a game update): look for BATTLE LOG often
                        # while the game has the focus, not every 1.5 s.
                        time.sleep(HUDLESS_POLL_S)
                    else:
                        time.sleep(COLD_POLL_S)
                except Exception as exc:  # never let the thread die
                    self.log(f"Auto-export loop error: {exc}")
                    time.sleep(3)

    # ── conceded battles ───────────────────────────────────────────────
    def _watch_for_menu(self, battle_since, hud_seen_at):
        """The HUD went away with no end screen: if the main menu shows up,
        the battle ended without one (a concede). Stops as soon as the HUD
        comes back (a deck search covered it) or the end screen is handled."""
        try:
            from RankDetector import RankDetector
            detector = RankDetector()
            deadline = time.time() + MENU_WATCH_S
            while time.time() < deadline and not self._stop.is_set():
                if self._battle_since != battle_since or self._last_hud_at > hud_seen_at:
                    return
                try:
                    on_menu = detector.is_on_main_menu(validation_method="auto")
                except Exception:
                    on_menu = False
                if on_menu and self._battle_since == battle_since and self._last_hud_at <= hud_seen_at:
                    self._battle_since = None
                    self.log("Main menu after a battle with no end screen - asking if you conceded.")
                    self.on_menu_without_end(battle_since)
                    return
                time.sleep(MENU_CHECK_EVERY_S)
        except Exception as exc:
            self.log(f"Concede check failed: {exc}")
        finally:
            self._menu_watch = None

    # ── one end-of-battle screen ───────────────────────────────────────
    def _handle_end_screen(self, hwnd, sct, rect, hit, last_hud=0.0):
        seen_at = time.time()
        white_since, self._white_since = self._white_since, None
        self.log(f"BATTLE LOG button visible (score {hit[2]:.2f}).")
        self._screenshot_end_screen(sct, rect)

        # Did the user already export THIS battle? "This battle" = since the
        # in-battle HUD was last seen, or the last 25 s if the HUD was never
        # detected (unusual arena themes).
        battle_ended = last_hud if last_hud else seen_at - USER_EXPORT_GRACE_S
        if self._captured_since(battle_ended):
            self.log("Battle log already on clipboard - nothing to click.")
            self._drop_cover()
            return

        # Cover Continue before anything else whenever the game shows there,
        # focused or not: the click that brings the game to the front would
        # otherwise press Continue. Never click into another app, though.
        early = self._cover is not None
        if self._cover is None and can_cover_continue(hwnd, rect):
            self._cover = self.launch_blocker(wait_s=0)
        deadline = time.time() + FOREGROUND_WAIT_S
        if not is_foreground(hwnd):
            self.log(f"Waiting for the game to be in front (in front: {_foreground_name()}).")
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
            if white_since is not None and early:
                self.log(f"Continue covered since the white flash ({seen_at - white_since:.2f}s before BATTLE LOG).")
            elif early:
                self.log("Continue covered on the template hit, before the text check.")
            else:
                self.log("Continue covered as soon as BATTLE LOG was confirmed.")
            self.wait_blocker(blocker)
        else:
            blocker = self.launch_blocker()
        try:
            exported = self._click_sequence(sct, hwnd, rect, seen_at)
            self.log("Auto-export complete." if exported else "Auto-export did not confirm a clipboard capture.")
        finally:
            # Reload a hidden standby blocker first, so a re-detected end
            # screen (or the next battle) never needs a cold start.
            self.prewarm_blocker()
            self.close_blocker(blocker)

    END_SHOT_GAP_S = 90   # one picture per end screen, even if it's seen again

    def _screenshot_end_screen(self, sct, rect):
        """Auto Screenshot (Limitless tab): the end screen of a tournament
        game, saved before anything is clicked."""
        try:
            import end_screens
            if time.time() - getattr(self, "_last_end_shot", 0.0) < self.END_SHOT_GAP_S:
                return
            opponent = end_screens.tournament_opponent()
            if not opponent or not end_screens.enabled():
                return
            self._last_end_shot = time.time()
            end_screens.save(sct.grab(rect), opponent, self.log)
        except Exception as exc:
            self.log(f"End screen screenshot failed: {exc}")

    def _button_still_there(self, sct, rect):
        """Template only: this end screen already passed the OCR check, and
        re-reading the text mid-animation failed often enough (score 0.95-1.00,
        text unreadable) to abort real exports as "user pressed Continue"."""
        return self._find(sct, BATTLE_LOG, rect, self._bottom_half(rect))

    @staticmethod
    def _wait_for_button_release():
        """Never start a hold while the player is holding the left button:
        the hold would swallow its release."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            give_up = time.time() + BUTTON_HELD_WAIT_S
            while user32.GetAsyncKeyState(0x01) & 0x8000 and time.time() < give_up:
                time.sleep(0.02)
        except Exception:
            pass

    def _hold_input(self):
        """The player's mouse and keyboard, held for one click (the friend
        request's lock: low-level hooks, injected input passes, Esc stops)."""
        try:
            from ptcgl_friend import InputBlocker
            return InputBlocker(on_escape=self._escaped.set, max_s=HOLD_MAX_S)
        except Exception:
            import contextlib
            return contextlib.nullcontext()

    def _click(self, x, y):
        self._wait_for_button_release()
        with self._hold_input():
            AutoClicker.physical_click(x, y)

    def _click_sequence(self, sct, hwnd, rect, seen_at):
        """BATTLE LOG -> export, retried until the log is on the clipboard.
        A click of the user's that closes the popup, or focus moving away for
        a moment, only costs a retry; the sequence ends when the log lands,
        the end screen is gone (Continue pressed), or after SEQUENCE_MAX_S."""
        self._capture_event.clear()
        self._escaped.clear()
        deadline = time.time() + SEQUENCE_MAX_S
        last_open = last_export = 0.0
        opens = exports = 0
        gone_since = None
        waiting_focus = False
        while time.time() < deadline and not self._stop.is_set():
            if self._captured_since(seen_at):
                return True
            if self._escaped.is_set():
                self.log("Esc pressed - auto-export stopped (export manually).")
                return False
            if not is_foreground(hwnd):
                if not waiting_focus:
                    self.log("Game lost focus - waiting for it to come back.")
                    waiting_focus = True
                time.sleep(0.2)
                continue
            waiting_focus = False
            now = time.time()
            export = self._find(sct, EXPORT, rect)
            if export:
                gone_since = None
                if now - last_export >= CAPTURE_CONFIRM_S:
                    self._click(export[0], export[1])
                    exports += 1
                    last_export = time.time()
                    self.log(f"Clicked export at ({export[0]},{export[1]})" + (f" (try {exports})" if exports > 1 else "") + ".")
                    if self._capture_event.wait(CAPTURE_CONFIRM_S):
                        return True
                    continue
            else:
                hit = self._button_still_there(sct, rect)
                if hit:
                    gone_since = None
                    if now - last_open >= REOPEN_EVERY_S:
                        self._click(hit[0], hit[1])
                        opens += 1
                        last_open = time.time()
                        self.log(f"Clicked BATTLE LOG at ({hit[0]},{hit[1]})" + (f" (try {opens})" if opens > 1 else "") + ".")
                else:
                    gone_since = gone_since or now
                    if now - gone_since >= GONE_S:
                        self.log("End screen gone before the export (Continue pressed?).")
                        return self._captured_since(seen_at)
            time.sleep(0.05)
        if not self._captured_since(seen_at):
            self.log(f"Export not confirmed after {SEQUENCE_MAX_S}s "
                     f"({opens} BATTLE LOG and {exports} export clicks).")
        return self._captured_since(seen_at)
