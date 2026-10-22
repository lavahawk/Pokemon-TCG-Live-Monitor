"""Tests for the HUD buddy's hidden meters and .pet_state.json (run: python test_pet_state.py).

No widget is created (no QApplication): the meter methods of PetWidget are
borrowed by a small stand-in class. pet.STATE_FILE is redirected to a temp
file, so the user's .pet_state.json is never read or written.
"""
import atexit
import json
import os
import random
import shutil
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TMP = tempfile.mkdtemp(prefix="ptcgl_test_pet_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

import pet

pet.STATE_FILE = os.path.join(TMP, ".pet_state.json")

DEFAULTS = {"games": 0, "fed_game": 0, "full_for": 3, "happiness": 60.0, "energy": 80.0, "level": 5,
            "candy_ready_at": 0.0, "recalled": False, "streak": 0, "gloom": 0.0}


def write_state(text):
    with open(pet.STATE_FILE, "w", encoding="utf-8") as handle:
        handle.write(text)


def read_state():
    with open(pet.STATE_FILE, "r", encoding="utf-8") as handle:
        return json.load(handle)


def clear_state():
    if os.path.exists(pet.STATE_FILE):
        os.remove(pet.STATE_FILE)


class FakePet:
    """PetWidget's meter logic without Qt: real methods, stubbed animations."""
    mood = pet.PetWidget.mood
    _meter = pet.PetWidget._meter
    react = pet.PetWidget.react
    menu_seen = pet.PetWidget.menu_seen
    _finish_eating = pet.PetWidget._finish_eating
    _pick_treat = pet.PetWidget._pick_treat
    sadness = pet.PetWidget.sadness
    _show_result = pet.PetWidget._show_result
    _pick_fresh = pet.PetWidget._pick_fresh

    def __init__(self, **mem):
        self.mem = dict(DEFAULTS, **mem)  # fresh meters, not whatever an earlier test saved
        self.portraits, self.sheets = {}, {}
        self.state, self.recalled, self.battle, self.speed_mul = "idle", False, False, 1.0
        self.berry, self.after_walk, self.y_off, self.zs = None, None, 0.0, []
        self.hyper_until = self.anger_at = self.shake_until = 0.0
        self.cloud_until = self.tears_until = self.grumble_until = 0.0
        self._last_pick = {}
        self.calls = []

    def _stub(name):
        def record(self, *args, **kwargs):
            self.calls.append(name)
        return record

    _love = _stub("love")
    say = _stub("say")
    _celebrate = _stub("celebrate")
    _shiny_burst = _stub("shiny")
    walk_to = _stub("walk_to")
    _enter = _stub("enter")
    _release = _stub("release")
    _win_reaction = _stub("win")
    _loss_reaction = _stub("loss")
    _confetti = _stub("confetti")

    def _later(self, ms, fn):
        self.calls.append("later")

    def _nap_spot(self):
        return 100.0


# ── load / save ────────────────────────────────────────────────────────────
def test_missing_or_broken_file_gives_defaults():
    clear_state()
    assert pet._load_state() == DEFAULTS
    for junk in ("", "{not json", '{"games": '):
        write_state(junk)
        assert pet._load_state() == DEFAULTS, repr(junk)
    clear_state()


def test_values_are_coerced_to_the_default_types():
    write_state(json.dumps({"games": 7, "fed_game": "4", "happiness": 55, "energy": "12.5", "level": None,
                            "full_for": "three", "recalled": True, "extra": "kept out"}))
    state = pet._load_state()
    assert state["games"] == 7 and state["fed_game"] == 4
    assert state["happiness"] == 55.0 and isinstance(state["happiness"], float)
    assert state["energy"] == 12.5
    assert state["level"] == 5 and state["full_for"] == 3  # unusable values: defaults
    assert state["recalled"] is True and "extra" not in state
    clear_state()


def test_save_then_load_round_trip():
    clear_state()
    state = dict(DEFAULTS, games=12, fed_game=10, happiness=99.5, level=8, recalled=True,
                 candy_ready_at=time.time() + 60)
    pet._save_state(state)
    assert read_state() == state and pet._load_state() == state


def test_save_to_unwritable_path_is_silent():
    saved = pet.STATE_FILE
    pet.STATE_FILE = os.path.join(TMP, "no", "such", "dir", "state.json")
    try:
        pet._save_state(dict(DEFAULTS))  # OSError swallowed
    finally:
        pet.STATE_FILE = saved


# ── mood and meters ────────────────────────────────────────────────────────
def test_mood_thresholds():
    assert FakePet().mood() == "fed"
    assert FakePet(games=3, fed_game=0).mood() == "fed"       # hunger == full_for
    assert FakePet(games=4, fed_game=0).mood() == "hungry"    # hunger > full_for
    assert FakePet(games=6, fed_game=0).mood() == "hungry"    # full_for + 3: still hungry
    assert FakePet(games=7, fed_game=0).mood() == "angry"
    assert FakePet(games=10, fed_game=4, full_for=6).mood() == "fed"
    assert FakePet(happiness=39.9).mood() == "hungry" and FakePet(happiness=40.0).mood() == "fed"
    assert FakePet(happiness=14.9).mood() == "angry"


def test_meter_clamps_to_0_100():
    p = FakePet(happiness=95.0, energy=3.0)
    p._meter("happiness", 20)
    p._meter("energy", -10)
    assert p.mem["happiness"] == 100.0 and p.mem["energy"] == 0.0
    p._meter("energy", 0.5)
    assert p.mem["energy"] == 0.5


# ── battles ────────────────────────────────────────────────────────────────
def test_react_counts_games_and_moves_happiness():
    clear_state()
    p = FakePet()
    p.battle, p.speed_mul = True, 0.45
    p.react("Win")
    assert p.mem["games"] == 1 and p.mem["happiness"] == 63.0
    assert p.battle is False and p.speed_mul == 1.0 and "win" in p.calls
    assert read_state()["games"] == 1  # saved right away
    p.calls = []
    p.react("Loss")
    assert p.mem["happiness"] == 60.0 and "loss" in p.calls and "win" not in p.calls
    p.react("Tie")  # neither: no celebration, no mope
    assert p.mem["games"] == 3 and p.mem["happiness"] == 57.0


def test_react_when_hungry_costs_more_happiness():
    p = FakePet(games=3, fed_game=0)  # the 4th game makes it hungry
    p.react("loss")
    assert p.mood() == "hungry" and p.mem["happiness"] == 60.0 - 3 - 8


def test_react_while_recalled_or_in_ball():
    clear_state()
    p = FakePet(recalled=True)
    p.recalled = True
    p.react("Win")
    assert p.mem["games"] == 1 and p.calls == [] and read_state()["recalled"] is True
    q = FakePet()
    q.state = "ball"
    q.react("Win")
    assert q._pending_result == "Win" and q.calls == []  # played once it's back out
    q.menu_seen()
    assert q.calls == ["release"]
    games = q.mem["games"]
    q.state = "idle"
    q._show_result(q._pending_result)  # replayed once it's out: the game isn't counted twice
    assert q.mem["games"] == games and "win" in q.calls


# ── treats ─────────────────────────────────────────────────────────────────
def test_treat_table():
    assert sum(w for w, _c, _fx in pet.TREATS.values()) == 100
    assert all(fx.get("full", 0) >= 3 for _w, _c, fx in pet.TREATS.values())


def test_berry_feeds_and_applies_effects():
    clear_state()
    p = FakePet(games=9, fed_game=0, happiness=30.0, energy=50.0)
    assert p.mood() == "angry"
    p.berry = [0, 0, 0, True, "Sitrus"]
    p._finish_eating()
    assert p.berry is None and p.mem["fed_game"] == 9 and p.mem["full_for"] == 6
    assert p.mem["happiness"] == 52.0 and p.mem["energy"] == 65.0 and p.mood() == "fed"
    assert read_state()["fed_game"] == 9
    q = FakePet(happiness=20.0)
    q.anger_at = q.shake_until = 123.0
    q.berry = [0, 0, 0, True, "Pecha"]
    q._finish_eating()
    assert q.mem["happiness"] == 50.0 and q.anger_at == 0.0  # calm: grumpiness gone
    r = FakePet()
    r.berry = [0, 0, 0, True]  # old 4-item berry = Oran
    r._finish_eating()
    assert r.mem["happiness"] == 70.0 and r.mem["full_for"] == 3
    s = FakePet()
    s.berry = [0, 0, 0, True, "Cheri"]
    s._finish_eating()
    assert s.hyper_until > time.monotonic() + 50
    FakePet()._finish_eating()  # no berry: nothing happens


def test_rare_candy_levels_up_and_starts_cooldown():
    clear_state()
    p = FakePet(happiness=10.0, energy=5.0, level=5)
    p.berry = [0, 0, 0, True, "Rare Candy"]
    before = time.time()
    p._finish_eating()
    assert p.mem["level"] == 6 and p.mem["happiness"] == 100.0 and p.mem["energy"] == 100.0
    assert p.mem["full_for"] == 6
    assert before + pet.RARE_CANDY_COOLDOWN_S <= p.mem["candy_ready_at"] <= time.time() + pet.RARE_CANDY_COOLDOWN_S
    assert read_state()["level"] == 6


def test_pick_treat_respects_candy_cooldown():
    saved = pet.random
    try:
        pet.random = types.SimpleNamespace(random=lambda: 0.0, choices=random.choices)  # always rolls a candy
        assert FakePet(candy_ready_at=0.0)._pick_treat() == "Rare Candy"
        assert FakePet(candy_ready_at=time.time() + 600)._pick_treat() in pet.TREATS
        pet.random = types.SimpleNamespace(random=lambda: 0.99, choices=random.choices)
        assert FakePet()._pick_treat() in pet.TREATS
    finally:
        pet.random = saved


def test_regression_non_object_state_and_string_bools():
    for raw in ("null", "[]", '"x"'):
        with open(pet.STATE_FILE, "w", encoding="utf-8") as handle:
            handle.write(raw)
        assert pet._load_state()["recalled"] is False
    with open(pet.STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump({"recalled": "false"}, handle)
    assert pet._load_state()["recalled"] is False
    pet._save_state(dict(pet._load_state(), level=9))
    assert pet._load_state()["level"] == 9 and not os.path.exists(pet.STATE_FILE + ".tmp")


# ── streaks, gloom, variety ───────────────────────────────────────────────
def test_streaks_and_gloom():
    clear_state()
    p = FakePet()
    for _ in range(3):
        p.react("Loss")
    assert p.mem["streak"] == -3 and p.mem["gloom"] == 14 + 18 + 22 and p.sadness() == "sad"
    p.react("Loss")
    p.react("Loss")
    assert p.mem["streak"] == -5 and p.sadness() == "depressed"
    gloom = p.mem["gloom"]
    p.react("Win")  # breaking a losing run: a big relief
    assert p.mem["streak"] == 1 and p.mem["gloom"] == max(0.0, gloom - 40)
    p.react("Win")
    p.react("Tie")  # a tie leaves the streak alone
    assert p.mem["streak"] == 2 and read_state()["streak"] == 2


def test_sadness_thresholds():
    assert FakePet().sadness() == "ok"
    assert FakePet(gloom=40.0).sadness() == "sad" and FakePet(streak=-3).sadness() == "sad"
    assert FakePet(gloom=70.0).sadness() == "depressed" and FakePet(streak=-5).sadness() == "depressed"


def test_reactions_never_repeat_back_to_back():
    p = FakePet()
    picks = [p._pick_fresh("win", pet.WIN_REACTIONS) for _ in range(200)]
    assert all(a != b for a, b in zip(picks, picks[1:])) and set(picks) == set(pet.WIN_REACTIONS)
    picks = [p._pick_fresh("loss", pet.LOSS_REACTIONS) for _ in range(300)]
    assert all(a != b for a, b in zip(picks, picks[1:])) and set(picks) == set(pet.LOSS_REACTIONS)


def test_new_berries():
    clear_state()
    lum = FakePet(gloom=80.0)
    lum.cloud_until = 999.0
    lum.berry = [0, 0, 0, True, "Lum"]
    lum._finish_eating()
    assert lum.mem["gloom"] == 0.0 and lum.cloud_until == 0.0
    colbur = FakePet()
    colbur.berry = [0, 0, 0, True, "Colbur"]
    colbur._finish_eating()
    assert "later" in colbur.calls  # the nap is scheduled
    enigma = FakePet()
    enigma.berry = [0, 0, 0, True, "Enigma"]
    enigma._finish_eating()
    assert enigma.mem["fed_game"] == 0 and "say" in enigma.calls
    rare = [n for n, (_w, _c, fx) in pet.TREATS.items() if fx.get("fx")]
    assert pet.TREATS["Oran"][0] < 60 and {"Cheri", "Sitrus", "Lum", "Colbur", "Enigma"} <= set(rare)


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
