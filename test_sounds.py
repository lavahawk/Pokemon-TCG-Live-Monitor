"""Tests for sounds.py (run: python test_sounds.py). Nothing is played."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sounds


def test_default_is_the_two_note_ding():
    assert sounds.DEFAULT_SOUND == "chime" and sounds.SOUNDS["chime"] == "Ding"
    assert sounds.SOUNDS["ding"] == "Chime"  # the recording kept its stored key


def test_every_synthesised_sound_is_a_valid_wav():
    for key in sounds.SOUNDS:
        if key == "ding":
            assert os.path.exists(sounds.DING_FILE)
            continue
        data = sounds.wav_bytes(key, 60)
        assert data[:4] == b"RIFF" and data[8:12] == b"WAVE", key
        assert struct.unpack("<I", data[40:44])[0] == len(data) - 44, key
        assert 0.05 < (len(data) - 44) / 2 / sounds.RATE < 1.5, key


def test_volume_scales_and_zero_is_silent():
    loud, quiet = sounds.wav_bytes("coindrop", 100), sounds.wav_bytes("coindrop", 20)
    peak = lambda d: max(abs(v) for v in struct.unpack(f"<{(len(d) - 44) // 2}h", d[44:]))
    assert peak(loud) > peak(quiet) > 0
    assert peak(sounds.wav_bytes("bubblepop", 0)) == 0


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
