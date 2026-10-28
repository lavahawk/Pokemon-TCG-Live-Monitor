"""
Import sounds: what plays when a battle log is saved.

Settings (.app_settings.json):
  import_sound_enabled  bool   (default True)
  import_sound          one of SOUNDS keys (default "chime")
  import_sound_volume   0-100  (default 60)

Every sound except the "ding" key (ding.mp3, played with pygame) is
synthesised, so there is nothing to ship or lose. No Qt here: the monitor
imports it.

The keys are what .app_settings.json stores, so they never change; only the
labels do. Since 2.10 the "chime" key (two notes) is labelled Ding and is the
default, and the "ding" key (the recording) is labelled Chime.
"""

import math
import os
import struct
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DING_FILE = os.path.join(BASE_DIR, "ding.mp3")
RATE = 44100

# key (stored, never renamed) -> label shown in Settings → Sound
SOUNDS = {
    "chime": "Ding",
    "ding": "Chime",
    "coin": "Coin",
    "coindrop": "Coin drop",
    "pop": "Pop",
    "bubblepop": "Bubble pop",
    "levelup": "Level up",
    "bubble": "Bubbles",
}
DEFAULT_SOUND = "chime"
DEFAULT_VOLUME = 60

_cache = {}


def _tone(freq, length, *, wave="sine", decay=10.0, attack=0.005, slide=0.0):
    """Mono float samples of one note. slide: Hz/s pitch glide."""
    out = []
    phase = 0.0
    for i in range(int(length * RATE)):
        t = i / RATE
        f = freq + slide * t
        phase += 2 * math.pi * f / RATE
        if wave == "square":
            s = 1.0 if math.sin(phase) >= 0 else -1.0
            s *= 0.45
        elif wave == "triangle":
            s = 2 / math.pi * math.asin(math.sin(phase))
        else:
            s = math.sin(phase) + 0.18 * math.sin(2 * phase)
        out.append(s * min(1.0, t / attack) * math.exp(-t * decay))
    return out


def _mix(parts, total):
    """parts: [(start_s, samples)] -> one track of `total` seconds."""
    track = [0.0] * int(total * RATE)
    for start, samples in parts:
        first = int(start * RATE)
        for i, s in enumerate(samples):
            if first + i >= len(track):
                break
            track[first + i] += s
    return track


def _clink(length, partials, decay, amp=1.0):
    """A struck bit of metal: inharmonic partials, the high ones dying first."""
    out = []
    for i in range(int(length * RATE)):
        t = i / RATE
        s = sum(a * math.sin(2 * math.pi * f * t) * math.exp(-t * decay * (f / partials[0][0]) ** 0.5)
                for f, a in partials)
        out.append(amp * s * min(1.0, t / 0.0008))
    return out


def _coin_drop():
    """A coin landing on a table: a bright first hit, bounces that come
    faster and softer, then a short spin-down rattle."""
    partials = ((2637.0, 1.0), (3960.0, 0.55), (5280.0, 0.32), (7112.0, 0.18))
    parts, t, gap, amp = [], 0.0, 0.16, 1.0
    for _ in range(6):
        parts.append((t, _clink(0.22, partials, 18, amp)))
        t += gap
        gap *= 0.62
        amp *= 0.6
    for k in range(10):  # the wobble as it settles
        parts.append((t + k * 0.022 * (1 - k * 0.05), _clink(0.05, partials, 60, 0.12 * (1 - k / 10))))
    return _mix(parts, t + 0.45)


def _bubble_pop():
    """One round bubble pop: a tiny click, then a tone that sweeps up fast
    (how a bubble sounds as it bursts) and dies out."""
    out = []
    phase, f0, f1, sweep = 0.0, 320.0, 1500.0, 0.045
    for i in range(int(0.11 * RATE)):
        t = i / RATE
        f = f0 * (f1 / f0) ** min(1.0, t / sweep)
        phase += 2 * math.pi * f / RATE
        s = math.sin(phase) * min(1.0, t / 0.002) * math.exp(-t * 34)
        if i < 60:  # the click of the film breaking (deterministic, no random)
            s += 0.35 * math.sin(i * 12.9898) * (1 - i / 60)
        out.append(s)
    return _mix([(0.0, out)], 0.13)


def _build(key):
    if key == "coindrop":
        return _coin_drop()
    if key == "bubblepop":
        return _bubble_pop()
    if key == "chime":
        return _mix([(0.0, _tone(880.0, 0.16, decay=11)),
                     (0.075, _tone(1318.5, 0.30, decay=11))], 0.40)
    if key == "coin":
        return _mix([(0.0, _tone(987.8, 0.08, wave="square", decay=4)),
                     (0.07, _tone(1318.5, 0.30, wave="square", decay=9))], 0.38)
    if key == "pop":
        return _mix([(0.0, _tone(420.0, 0.09, decay=40, attack=0.002, slide=2600))], 0.12)
    if key == "levelup":
        notes = (523.3, 659.3, 784.0, 1046.5)
        return _mix([(i * 0.07, _tone(f, 0.22, wave="triangle", decay=9))
                     for i, f in enumerate(notes)], 0.50)
    if key == "bubble":
        return _mix([(0.0, _tone(600.0, 0.07, decay=35, slide=4000)),
                     (0.09, _tone(800.0, 0.07, decay=35, slide=4500)),
                     (0.18, _tone(1000.0, 0.09, decay=30, slide=5000))], 0.30)
    return None


def wav_bytes(key, volume=DEFAULT_VOLUME):
    """16-bit mono WAV of a synthesised sound, or None (unknown / "ding")."""
    volume = max(0, min(100, int(volume)))
    cache_key = (key, volume)
    if cache_key in _cache:
        return _cache[cache_key]
    samples = _build(key)
    if not samples:
        return None
    peak = max(abs(s) for s in samples) or 1.0
    gain = 0.45 * volume / 100.0
    frames = b"".join(struct.pack("<h", int(s / peak * gain * 32767)) for s in samples)
    header = (b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVE"
              + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
              + b"data" + struct.pack("<I", len(frames)))
    _cache[cache_key] = header + frames
    return _cache[cache_key]


def _play_blocking(key, volume):
    if key == "ding":
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        sound = pygame.mixer.Sound(DING_FILE)
        sound.set_volume(max(0, min(100, int(volume))) / 100.0)
        sound.play()
        return
    data = wav_bytes(key, volume)
    if data:
        import winsound
        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)


def play(key=None, volume=None):
    """Play a sound on a background thread (never raises)."""
    key = key if key in SOUNDS else DEFAULT_SOUND
    volume = DEFAULT_VOLUME if volume is None else volume

    def _run():
        try:
            _play_blocking(key, volume)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def play_import_sound(settings=None):
    """The battle-saved sound, as configured. Silent when turned off."""
    if settings is None:
        try:
            from app_settings import load_app_settings
            settings = load_app_settings()
        except Exception:
            settings = {}
    if not settings.get("import_sound_enabled", True):
        return
    play(settings.get("import_sound", DEFAULT_SOUND),
         settings.get("import_sound_volume", DEFAULT_VOLUME))
