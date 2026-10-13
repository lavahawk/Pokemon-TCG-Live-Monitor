"""
Opponent-deck confirmation: the files and helpers behind the overlay's
"Opponent deck" card (deck_popup.py). No Qt here, so the parser and the
monitor can import it cheaply.

Flow
  AIParseBattleLog saves a battle  -> write_request(battle_id, deck, ...)
  TCGLiveMonitor sees the main menu -> mark_menu_seen()
  OverlayUI polls both files       -> shows the card, fades it once the menu
                                      is seen, or keeps asking when the deck
                                      still needs to be entered.
"""

import json
import math
import os
import struct
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "Logs")
REQUEST_FILE = os.path.join(LOG_DIR, ".deck_confirm.json")
MENU_SEEN_FILE = os.path.join(LOG_DIR, ".menu_seen")
LIMITLESS_CACHE_FILE = os.path.join(BASE_DIR, ".meta_cache_limitless_standard.json")

REQUEST_MAX_AGE_S = 15 * 60  # an older request is stale (e.g. overlay restarted later)
OTHER = "Other"


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(tmp, path)


def write_request(battle_id, deck, *, source, needs_input, my_deck=None, result=None):
    """Ask the overlay to show (or ask for) the opponent's deck of a saved battle.

    source: "ai" (picked by the AI parser), "guess" (local guess from the log)
            or "none" (nothing to go on).
    """
    _write_json(REQUEST_FILE, {
        "battle_id": battle_id,
        "deck": deck or "",
        "source": source,
        "needs_input": bool(needs_input),
        "my_deck": my_deck or "",
        "result": result or "",
        "created": time.time(),
        "handled": False,
    })


def read_request():
    """The pending request, or None when there is none / it is stale / handled."""
    try:
        with open(REQUEST_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("handled") or not data.get("battle_id"):
        return None
    if time.time() - float(data.get("created") or 0) > REQUEST_MAX_AGE_S:
        return None
    return data


def mark_handled(battle_id):
    """The user confirmed / fixed / dismissed the card: don't show it again."""
    try:
        with open(REQUEST_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and data.get("battle_id") == battle_id:
            data["handled"] = True
            _write_json(REQUEST_FILE, data)
    except (OSError, ValueError):
        pass


def mark_menu_seen():
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(MENU_SEEN_FILE, "w", encoding="utf-8") as handle:
            handle.write(f"{time.time():.3f}")
    except OSError:
        pass


def menu_seen_at():
    try:
        with open(MENU_SEEN_FILE, "r", encoding="utf-8") as handle:
            return float(handle.read().strip() or 0)
    except (OSError, ValueError):
        return 0.0


def known_deck_names(db=None):
    """Names for autocomplete: opponent decks you've recorded (most played
    first), then Limitless archetypes (by share). Placeholders left out."""
    names, seen = [], set()

    def add(name):
        name = " ".join(str(name or "").split())
        key = name.casefold()
        if not name or key in seen or key.startswith("unknown"):
            return
        seen.add(key)
        names.append(name)

    if db is not None:
        try:
            conn = db._connect()
            try:
                rows = conn.execute("SELECT opponent_deck, COUNT(*) c FROM battles "
                                    "GROUP BY opponent_deck ORDER BY c DESC").fetchall()
            finally:
                conn.close()
            for deck, _count in rows:
                add(deck)
        except Exception:
            pass
    try:
        with open(LIMITLESS_CACHE_FILE, "r", encoding="utf-8") as handle:
            rows = (json.load(handle) or {}).get("rows") or []
        for row in sorted(rows, key=lambda r: -(r.get("share") or 0)):
            add(row.get("deck"))
    except Exception:
        pass
    add(OTHER)
    return names


def canonical_name(text, names):
    """The known spelling of `text` (case/space-insensitive), else None."""
    key = " ".join(str(text or "").split()).casefold()
    return next((n for n in names if n.casefold() == key), None)


# ── confirm chime ────────────────────────────────────────────────────────
_chime = {}


def chime_wav():
    """A soft two-note rising chime (A5 -> E6), 16-bit mono WAV bytes.
    Synthesised once, so there is no sound file to ship or lose."""
    if "wav" in _chime:
        return _chime["wav"]
    rate = 44100
    notes = ((880.0, 0.0, 0.16), (1318.5, 0.075, 0.30))  # (Hz, start s, length s)
    total = int(rate * 0.40)
    samples = [0.0] * total
    for freq, start, length in notes:
        first = int(start * rate)
        for i in range(int(length * rate)):
            if first + i >= total:
                break
            t = i / rate
            attack = min(1.0, t / 0.006)
            decay = math.exp(-t * 11.0)
            tone = math.sin(2 * math.pi * freq * t) + 0.18 * math.sin(4 * math.pi * freq * t)
            samples[first + i] += tone * attack * decay
    peak = max(abs(s) for s in samples) or 1.0
    volume = 0.22  # subtle
    frames = b"".join(struct.pack("<h", int(s / peak * volume * 32767)) for s in samples)
    header = (b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVE"
              + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
              + b"data" + struct.pack("<I", len(frames)))
    _chime["wav"] = header + frames
    return _chime["wav"]


def play_chime():
    def _play():
        try:
            import winsound
            winsound.PlaySound(chime_wav(), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()
