"""
Pokemon TCG Live Monitor - main process.

Runs at Windows login (pythonw, --headless) or in a console (debug mode).

Lifecycle
---------
1. Single-instance lock, PID file, output redirected to Logs/monitor.log when
   there is no console (pythonw has sys.stdin/stdout = None - that crashed the
   old version at import time; BUG-009).
2. IDLE: check every few seconds whether the game process is running. Nothing
   else runs, so the idle cost is one process scan per poll.
3. GAME RUNNING: start the overlay (once), the battle-end auto-export thread
   and the post-battle worker; watch the clipboard via the cheap Windows
   clipboard sequence number and only read text when it changes.
4. Battle log on the clipboard -> dedupe by content hash (DB-backed, BUG-002)
   -> save as UTF-8 (BUG-011) -> notify auto-export -> ding -> queue the
   parse + post-battle OCR on a worker thread so capture never blocks (BUG-018).

Debug: run in a console (Run_TCGLiveMonitor_Command_Prompt.bat) to see live
output; everything is also written to Logs/monitor.log.
"""

import argparse
import atexit
import hashlib
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime

###Version=2.4
from version import VERSION

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "Logs")
SOUND_FILE = os.path.join(BASE_DIR, "ding.mp3")
PARSER_SCRIPT = os.path.join(BASE_DIR, "AIParseBattleLog.py")
OVERLAY_SCRIPT = os.path.join(BASE_DIR, "OverlayUI.py")
BLOCKER_SCRIPT = os.path.join(BASE_DIR, "ContinueBlocker.py")
PID_FILE = os.path.join(BASE_DIR, ".monitor_pid")
LOCK_FILE = os.path.join(BASE_DIR, ".monitor_lock")
LAST_DECK_FILE = os.path.join(BASE_DIR, ".last_deck")
LAST_RANK_FILE = os.path.join(BASE_DIR, ".last_rank")
BLOCKER_DISMISS_FILE = os.path.join(LOG_DIR, ".blocker_dismiss")
BLOCKER_READY_FILE = os.path.join(LOG_DIR, ".blocker_ready")
BLOCKER_SHOW_FILE = os.path.join(LOG_DIR, ".blocker_show")
MONITOR_LOG = os.path.join(LOG_DIR, "monitor.log")
CLICKER_LOG = os.path.join(LOG_DIR, "autoclicker.log")

IDLE_POLL_S = 5            # game-process check while the game is closed
RUNNING_PROC_CHECK_S = 10  # game-process check while it is running
CLIPBOARD_POLL_S = 0.5
PARSER_TIMEOUT_S = 180
MENU_OCR_TIMEOUT_S = 120

os.makedirs(LOG_DIR, exist_ok=True)


# ───────────────────────────── output / logging ─────────────────────────────
def _rotate(path, max_bytes=2_000_000):
    try:
        if os.path.exists(path) and os.path.getsize(path) > max_bytes:
            backup = path + ".1"
            if os.path.exists(backup):
                os.remove(backup)
            os.replace(path, backup)
    except Exception:
        pass


class _Tee:
    """Write to the console (if any) and to Logs/monitor.log."""

    def __init__(self, console, logfile):
        self.console = console
        self.logfile = logfile

    def write(self, text):
        for stream in (self.console, self.logfile):
            if stream is not None:
                try:
                    stream.write(text)
                except Exception:
                    pass
        return len(text)

    def flush(self):
        for stream in (self.console, self.logfile):
            if stream is not None:
                try:
                    stream.flush()
                except Exception:
                    pass

    def isatty(self):
        return bool(self.console and getattr(self.console, "isatty", lambda: False)())


def setup_output():
    """Make print() safe under pythonw and mirror it to Logs/monitor.log."""
    _rotate(MONITOR_LOG)
    try:
        logfile = open(MONITOR_LOG, "a", encoding="utf-8", buffering=1)
    except Exception:
        logfile = None
    console_out, console_err = sys.stdout, sys.stderr
    for stream in (console_out, console_err):
        try:
            if stream is not None:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.stdout = _Tee(console_out, logfile)
    sys.stderr = _Tee(console_err, logfile)


def has_console():
    try:
        return bool(sys.stdin is not None and sys.stdin.isatty())
    except Exception:
        return False


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def alog(msg):
    """Auto-export events: Logs/autoclicker.log + main log."""
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    log(f"[AutoExport] {msg}")
    try:
        _rotate(CLICKER_LOG, 1_000_000)
        with open(CLICKER_LOG, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


# ───────────────────────────── single instance ─────────────────────────────
_lock_handle = None


def _pid_is_monitor(pid):
    try:
        import psutil
        proc = psutil.Process(pid)
        return proc.is_running() and "TCGLiveMonitor" in " ".join(proc.cmdline() or [])
    except Exception:
        return False


def acquire_single_instance():
    """Race-free on Windows (byte lock); PID-file check elsewhere."""
    global _lock_handle
    if os.name == "nt":
        try:
            import msvcrt
            handle = open(LOCK_FILE, "a+")
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                handle.close()
                return False
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
            _lock_handle = handle
            return True
        except Exception:
            pass
    try:
        with open(PID_FILE, "r") as fh:
            existing = int(fh.read().strip() or 0)
        if existing and existing != os.getpid() and _pid_is_monitor(existing):
            return False
    except Exception:
        pass
    return True


def release_single_instance():
    global _lock_handle
    if _lock_handle is not None:
        try:
            import msvcrt
            _lock_handle.seek(0)
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        try:
            _lock_handle.close()
        except Exception:
            pass
        _lock_handle = None
    for path in (LOCK_FILE, PID_FILE):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


# ───────────────────────────── battle log detection ─────────────────────────
RESULT_RE = re.compile(r"(?im)^.*\bwins\.\s*$")
OLD_TURN_RE = re.compile(r"Turn #\s*\d+\s*-\s*.+?'s Turn", re.IGNORECASE)
NEW_TURN_RE = re.compile(r"(?m)^[^\n]{1,40}'s Turn\s*$")
ACTION_RE = re.compile(r"\b(played|drew|attached|used|retreated|evolved|was Knocked Out|took a Prize card)\b")


def is_battle_log(text):
    if not text:
        return False
    normalized = text.replace("\r\n", "\n").strip()
    if len(normalized) < 120:
        return False
    has_result = bool(RESULT_RE.search(normalized))
    if OLD_TURN_RE.search(normalized) and has_result:
        return True
    has_setup = normalized.startswith("Setup") or "\nSetup\n" in f"\n{normalized}\n"
    return bool(has_setup and NEW_TURN_RE.search(normalized) and has_result
                and len(ACTION_RE.findall(normalized)) >= 3)


def looks_like_partial_log(text):
    """Only near-misses are kept for debugging (never arbitrary clipboard text)."""
    markers = sum(bool(x) for x in (
        "'s Turn" in text, text.lstrip().startswith("Setup"), "Prize card" in text,
        RESULT_RE.search(text), len(ACTION_RE.findall(text)) >= 3,
    ))
    return markers >= 3


def normalized_hash(text):
    from BattleDatabase import log_hash
    return log_hash(text)


# ───────────────────────────── clipboard ─────────────────────────────
def clipboard_sequence():
    """Windows clipboard change counter (cheap). None when unavailable."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        return int(ctypes.windll.user32.GetClipboardSequenceNumber())
    except Exception:
        return None


def read_clipboard():
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except Exception:
        return ""


# ───────────────────────────── helpers ─────────────────────────────
def set_low_priority(low):
    """Below-normal CPU priority while idling for the game; normal while it
    runs (so battle-end clicks are not delayed when the game is busy)."""
    if os.name != "nt":
        return
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if low else psutil.NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def play_sound_async():
    def _play():
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.Sound(SOUND_FILE).play()
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


def _no_window_flags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def gui_python():
    """pythonw.exe next to the current interpreter (no console window)."""
    exe = sys.executable or "python"
    if os.name == "nt" and exe.lower().endswith("python.exe"):
        candidate = exe[:-len("python.exe")] + "pythonw.exe"
        if os.path.exists(candidate):
            return candidate
    return exe


def write_text(path, value):
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(str(value))
    except Exception:
        pass


def read_int(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return int(handle.read().strip())
    except Exception:
        return None


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except Exception:
        return ""


_settings_cache = {"t": 0.0, "data": {}}


def app_setting(key, default):
    """Read a setting from .app_settings.json (cached for 3 s)."""
    now = time.time()
    if now - _settings_cache["t"] > 3:
        try:
            from app_settings import load_app_settings
            _settings_cache["data"] = load_app_settings()
        except Exception:
            _settings_cache["data"] = {}
        _settings_cache["t"] = now
    return _settings_cache["data"].get(key, default)


# ───────────────────────────── Continue blocker ─────────────────────────────
_standby_blocker = {"proc": None}


def _remove_files(*paths):
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def prewarm_blocker():
    """Start a hidden standby blocker during a battle (Qt fully loaded), so
    the end screen only needs a signal file to cover Continue (~30 ms)."""
    proc = _standby_blocker["proc"]
    if proc is not None and proc.poll() is None:
        return
    if not os.path.exists(BLOCKER_SCRIPT):
        return
    _remove_files(BLOCKER_SHOW_FILE)
    try:
        _standby_blocker["proc"] = subprocess.Popen(
            [gui_python(), BLOCKER_SCRIPT, "--standby", "--parent", str(os.getpid())],
            cwd=BASE_DIR, creationflags=_no_window_flags())
    except Exception as exc:
        alog(f"Standby blocker launch failed: {exc}")


def stop_standby_blocker():
    proc = _standby_blocker["proc"]
    _standby_blocker["proc"] = None
    if proc is not None and proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass


def launch_blocker(wait_s=4.0):
    """Cover the Continue button and wait until the blocker is in place.

    Uses the pre-warmed standby blocker when there is one (appears in one
    30 ms poll); otherwise starts a new one (Qt needs 1-2 s). The click
    sequence only starts once the blocker reports it is positioned.
    """
    _remove_files(BLOCKER_DISMISS_FILE, BLOCKER_READY_FILE)
    standby = _standby_blocker["proc"]
    _standby_blocker["proc"] = None
    if standby is not None and standby.poll() is None:
        proc, how = standby, "standby"
        write_text(BLOCKER_SHOW_FILE, time.time())
    else:
        if not os.path.exists(BLOCKER_SCRIPT):
            return None
        try:
            proc, how = subprocess.Popen([gui_python(), BLOCKER_SCRIPT], cwd=BASE_DIR,
                                         creationflags=_no_window_flags()), "cold start"
        except Exception as exc:
            alog(f"Continue blocker launch failed: {exc}")
            return None
    started = time.time()
    while time.time() - started < wait_s:
        if os.path.exists(BLOCKER_READY_FILE):
            alog(f"Continue blocker up after {time.time() - started:.2f}s ({how}).")
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    alog(f"Continue blocker not confirmed after {time.time() - started:.1f}s - continuing anyway.")
    return proc


def signal_blocker_dismiss():
    write_text(BLOCKER_DISMISS_FILE, time.time())


def close_blocker(proc):
    signal_blocker_dismiss()
    if proc is None:
        return
    def _reap():
        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    threading.Thread(target=_reap, daemon=True).start()


# ───────────────────────────── OCR (rank / deck) ─────────────────────────────
def detect_menu_stats(timeout_s, reason, update_battle_id=None):
    """Wait for the main menu, read deck + rank, store them.

    update_battle_id: if given, that exact battle row gets the post-battle
    rank and the OCR deck name (never "the newest row" - BUG-006).
    """
    try:
        from RankDetector import RankDetector, read_rank_confirmed, snap_deck_name
        from BattleDatabase import BattleDatabase
    except Exception as exc:
        log(f"OCR unavailable: {exc}")
        return
    detector = RankDetector()
    deadline = time.time() + timeout_s
    deck = None
    while time.time() < deadline:
        try:
            if detector.is_on_main_menu(validation_method="auto"):
                db = BattleDatabase()
                if not deck:
                    raw_deck = detector.extract_text("my_deck_name", silent=True)
                    deck = snap_deck_name(raw_deck, db.get_known_deck_names()) if raw_deck else None
                rank = read_rank_confirmed(detector, last_accepted=read_int(LAST_RANK_FILE))
                if rank is None and time.time() + 4 < deadline:
                    # After a battle the points counter animates for a few
                    # seconds, so consecutive reads disagree. Keep reading
                    # until it settles instead of giving up (BUG-040).
                    time.sleep(1)
                    continue
                if deck:
                    write_text(LAST_DECK_FILE, deck)
                if rank:
                    write_text(LAST_RANK_FILE, rank)
                    db.add_rank_update(rank, deck)
                if update_battle_id:
                    updates = {}
                    if rank:
                        updates["my_rank"] = rank
                    if deck:
                        updates["my_deck"] = deck
                    if updates:
                        db.update_battle_record(update_battle_id, updates=updates)
                log(f"Menu OCR ({reason}): deck={deck!r} rank={rank}" +
                    (f" -> battle #{update_battle_id}" if update_battle_id else ""))
                return
        except Exception as exc:
            log(f"Menu OCR error: {exc}")
        time.sleep(2)
    log(f"Menu OCR ({reason}): main menu not seen within {timeout_s}s.")


# ───────────────────────────── the monitor ─────────────────────────────
class Monitor:
    def __init__(self, args):
        self.args = args
        self.jobs = queue.Queue()
        self.overlay_proc = None
        self.overlay_starts = 0
        self.automation = None
        self.recent_hashes = {}  # hash -> time (fast path; DB is the source of truth)
        self.worker = threading.Thread(target=self._worker, daemon=True, name="BattleWorker")
        self.worker.start()

    # ── overlay ──
    def ensure_overlay(self):
        if self.args.no_overlay or not os.path.exists(OVERLAY_SCRIPT):
            return
        if self.overlay_proc is not None and self.overlay_proc.poll() is None:
            return
        if self.overlay_starts >= 5:
            return  # crashing repeatedly; see Logs/overlay_error.log
        self.overlay_starts += 1
        try:
            err = open(os.path.join(LOG_DIR, "overlay_error.log"), "a", encoding="utf-8")
            self.overlay_proc = subprocess.Popen([gui_python(), OVERLAY_SCRIPT], cwd=BASE_DIR,
                                                 stderr=err, creationflags=_no_window_flags())
            log("Overlay started.")
        except Exception as exc:
            log(f"Could not start overlay: {exc}")

    # ── auto export ──
    def ensure_automation(self):
        if self.automation is not None and self.automation.is_alive():
            return
        if not app_setting("auto_export_battle_log", True):
            return
        try:
            from BattleEndAutomation import BattleEndAutomation
            self.automation = BattleEndAutomation(
                alog, launch_blocker, close_blocker,
                enabled_fn=lambda: bool(app_setting("auto_export_battle_log", True)),
                prewarm_blocker=prewarm_blocker,
            )
            atexit.register(stop_standby_blocker)
            self.automation.start()
        except Exception as exc:
            alog(f"Auto-export unavailable: {exc}")
            self.automation = None

    # ── clipboard ──
    def handle_clipboard(self, text):
        # Your own deck exported from PTCGL (Export → Copy to clipboard):
        # remembered for the In Person tab's "Print your decklist".
        try:
            from decklists import is_ptcgl_decklist, save_decklist
            if is_ptcgl_decklist(text):
                deck = read_text(LAST_DECK_FILE) or None
                entry = save_decklist(text, deck)
                log(f"Decklist captured: {entry['deck']} ({entry['cards']} cards).")
                return
        except Exception as exc:
            log(f"Decklist capture failed: {exc}")
        if not is_battle_log(text):
            if len(text) >= 120 and looks_like_partial_log(text):
                stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                write_text(os.path.join(LOG_DIR, f"unmatched_{stamp}.txt"), text[:200_000])
                log("Clipboard looked like a partial battle log; saved for debugging.")
            return

        # Any battle log on the clipboard means the export happened.
        signal_blocker_dismiss()
        if self.automation is not None:
            self.automation.notify_log_captured()

        digest = normalized_hash(text)
        now = time.time()
        if digest in self.recent_hashes:
            log("Same battle log copied again - ignored.")
            return
        self.recent_hashes = {h: t for h, t in self.recent_hashes.items() if now - t < 6 * 3600}
        self.recent_hashes[digest] = now
        try:
            from BattleDatabase import BattleDatabase
            if BattleDatabase().has_log_hash(digest):
                log("Battle log already stored in the database - ignored.")
                return
        except Exception as exc:
            log(f"DB dedupe check failed: {exc}")

        path = self.save_log(text)
        log(f"Battle log saved: {os.path.basename(path)}")
        play_sound_async()
        self.jobs.put(path)

    @staticmethod
    def save_log(text):
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(LOG_DIR, f"battle_log_{stamp}.txt")
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(LOG_DIR, f"battle_log_{stamp}_{n}.txt")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text.replace("\r\n", "\n").strip() + "\n")
        return path

    # ── worker: parse + post-battle OCR ──
    def _worker(self):
        while True:
            path = self.jobs.get()
            try:
                battle_id = self.run_parser(path)
                detect_menu_stats(MENU_OCR_TIMEOUT_S, "after battle", update_battle_id=battle_id)
            except Exception as exc:
                log(f"Worker error: {exc}")

    @staticmethod
    def run_parser(path):
        cmd = [sys.executable, PARSER_SCRIPT, os.path.abspath(path)]
        try:
            result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=PARSER_TIMEOUT_S, creationflags=_no_window_flags())
        except subprocess.TimeoutExpired:
            log(f"Parser timed out after {PARSER_TIMEOUT_S}s.")
            return None
        except Exception as exc:
            log(f"Parser failed to start: {exc}")
            return None
        output = (result.stdout or "") + (result.stderr or "")
        for line in output.splitlines():
            if line.strip():
                log(f"[Parser] {line.rstrip()}")
        match = re.search(r"BATTLE_ID=(\d+)", output)
        return int(match.group(1)) if match else None

    # ── main loop ──
    def run(self):
        from game_window import is_game_process_running
        game_running = False
        last_proc_check = 0.0
        last_seq = None
        log("Waiting for Pokemon TCG Live...")
        set_low_priority(True)
        while True:
            now = time.time()
            interval = RUNNING_PROC_CHECK_S if game_running else IDLE_POLL_S
            if now - last_proc_check >= interval:
                last_proc_check = now
                running = is_game_process_running()
                if running and not game_running:
                    log("Pokemon TCG Live detected.")
                    ensure_username()  # no-op once saved; first run asks now, not at sign-in
                    set_low_priority(False)
                    self.ensure_overlay()
                    self.ensure_automation()
                    last_seq = clipboard_sequence()
                    threading.Thread(target=detect_menu_stats, args=(60, "startup"), daemon=True).start()
                elif not running and game_running:
                    log("Pokemon TCG Live closed. Idling.")
                    set_low_priority(True)
                game_running = running
                if game_running:
                    self.ensure_overlay()
                    self.ensure_automation()

            if not game_running:
                time.sleep(IDLE_POLL_S)
                continue

            seq = clipboard_sequence()
            if seq is None or seq != last_seq:
                last_seq = seq
                text = read_clipboard()
                if seq is None:
                    # Non-Windows fallback: only act on content changes.
                    if text == getattr(self, "_last_text", None):
                        time.sleep(CLIPBOARD_POLL_S)
                        continue
                    self._last_text = text
                if text:
                    try:
                        self.handle_clipboard(text)
                    except Exception as exc:
                        log(f"Clipboard handling error: {exc}")
            time.sleep(CLIPBOARD_POLL_S)


# ───────────────────────────── entry point ─────────────────────────────
def ensure_username():
    from app_settings import load_username, save_username
    username = load_username()
    if username:
        return username
    if has_console():
        while not username:
            username = input("First time setup\nEnter your TCG Live username: ").strip()
    else:
        from qt_dialogs import ask_string
        username = ask_string("TCG Live Monitor", "Enter your TCG Live username:") or ""
    if username:
        save_username(username)
    return username


def ocr_test():
    """--ocr-test: one-shot OCR diagnostic (used by the dashboard's button)."""
    from RankDetector import RankDetector
    detector = RankDetector()
    print("Game window:", detector.find_game_window())
    print("On main menu:", detector.is_on_main_menu(validation_method="auto", debug=True))
    print("Deck:", detector.extract_text("my_deck_name", debug=True))
    print("Rank:", detector.extract_rank(debug=True))
    print("Debug images saved next to the app (debug_*.png).")
    if has_console():
        input("Press Enter to close...")


def main():
    parser = argparse.ArgumentParser(description="Pokemon TCG Live Monitor")
    parser.add_argument("--headless", action="store_true", help="No console UI (used by auto-start)")
    parser.add_argument("--no-overlay", action="store_true", help="Do not start the overlay")
    parser.add_argument("--ocr-test", action="store_true", help="Run a one-shot OCR diagnostic and exit")
    args = parser.parse_args()

    setup_output()
    if args.ocr_test:
        ocr_test()
        return 0

    if not acquire_single_instance():
        log("Another monitor instance is already running - exiting.")
        return 0
    write_text(PID_FILE, os.getpid())

    try:
        from game_window import ensure_dpi_aware
        ensure_dpi_aware()
    except Exception:
        pass

    if has_console() and not args.headless:
        try:
            print("\033]0;PTCGL Monitor Console\007", end="")
            import pyfiglet
            print(pyfiglet.figlet_format("TCG Live Monitor"))
        except Exception:
            pass
    log(f"Monitor v{VERSION} starting (pid {os.getpid()}, {'console' if has_console() else 'headless'}).")
    if has_console() and not args.headless:
        ensure_username()
    # Headless (auto-start at sign-in): never block on a dialog before the game
    # is even open - the username is asked when Pokemon TCG Live is detected.

    try:
        Monitor(args).run()
    except KeyboardInterrupt:
        log("Stopped by user.")
    except Exception as exc:
        import traceback
        log(f"FATAL: {exc}\n{traceback.format_exc()}")
        raise
    finally:
        release_single_instance()
    return 0


if __name__ == "__main__":
    sys.exit(main())
