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
  BATTLE LOG seen on 2 consecutive frames ->
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

from AutoClicker import AutoClicker
from BattleState import check_hud
from game_window import GameWindowCache, is_foreground, is_game_process_running

BATTLE_LOG = "battle_log"
EXPORT = "battle_log_export"

HOT_WINDOW_S = 180
HOT_POLL_S = 0.25
COLD_POLL_S = 1.5
HUD_POLL_S = 1.5
USER_EXPORT_GRACE_S = 25
FOREGROUND_WAIT_S = 20
EXPORT_SEARCH_S = 6.0
CAPTURE_CONFIRM_S = 2.5
EXPORT_RETRIES = 2
REARM_ABSENT_S = 60


class BattleEndAutomation(threading.Thread):
    def __init__(self, log_fn, launch_blocker, close_blocker, enabled_fn=lambda: True):
        super().__init__(daemon=True, name="BattleEndAutomation")
        self.log = log_fn
        self.launch_blocker = launch_blocker
        self.close_blocker = close_blocker
        self.enabled_fn = enabled_fn
        self.clicker = AutoClicker()
        self.window = GameWindowCache(refresh_s=5.0)
        self._stop = threading.Event()
        self._capture_lock = threading.Lock()
        self._last_capture = 0.0
        self._capture_event = threading.Event()
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

    def _find(self, sct, name, rect, region=None):
        region = region or rect
        frame = np.asarray(sct.grab(region))
        return self.clicker.find_in_frame(name, frame, (region["left"], region["top"]), rect["height"])

    def _battle_log_visible(self, sct, rect):
        return self._find(sct, BATTLE_LOG, rect, self._bottom_half(rect))

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

                    hud, hits, _details = check_hud(rect, sct)
                    now = time.time()
                    if hud:
                        if not in_battle:
                            self.log(f"Battle HUD detected ({hits}/3).")
                        in_battle, last_hud, streak, armed = True, now, 0, True
                        time.sleep(HUD_POLL_S)
                        continue
                    in_battle = False

                    hit = self._battle_log_visible(sct, rect)
                    if not hit:
                        streak = 0
                        if not armed and now - absent_since >= REARM_ABSENT_S:
                            armed = True
                    else:
                        absent_since = now
                        streak += 1
                    if armed and streak >= 2:
                        self._handle_end_screen(hwnd, sct, rect, hit, last_hud)
                        armed, streak, last_hud = False, 0, 0.0
                        absent_since = time.time()
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
            return

        # Never click into another app: wait for the game to be focused.
        deadline = time.time() + FOREGROUND_WAIT_S
        while not is_foreground(hwnd):
            if time.time() > deadline or self._stop.is_set():
                self.log("Game not in foreground - skipped auto-export (export manually).")
                return
            if self._captured_since(seen_at):
                self.log("User exported while game was unfocused.")
                return
            time.sleep(0.25)

        blocker = self.launch_blocker()
        try:
            exported = self._click_sequence(sct, hwnd, rect, seen_at)
            self.log("Auto-export complete." if exported else "Auto-export did not confirm a clipboard capture.")
        finally:
            self.close_blocker(blocker)

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
