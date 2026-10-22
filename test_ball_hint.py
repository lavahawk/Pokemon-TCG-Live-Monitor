"""Tests for the mini GUI ball's buddy hint (run: python test_ball_hint.py).

The overlay's real methods on a stand-in object: no window, a fake clock,
the battle-start time and "is something inside" stubbed. Nothing is shown.
"""
import os
import random
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deck_confirm
import OverlayUI as O

CLOCK = {"mono": 1000.0, "wall": 5000.0}
O.time = types.SimpleNamespace(monotonic=lambda: CLOCK["mono"], time=lambda: CLOCK["wall"])


class FakeOverlay:
    BALL_HINT_ODDS = O.MinimalOverlay.BALL_HINT_ODDS
    BALL_HINT_WINDOW_S = O.MinimalOverlay.BALL_HINT_WINDOW_S
    _game_ended_for_ball_hint = O.MinimalOverlay._game_ended_for_ball_hint
    _poll_ball_hint = O.MinimalOverlay._poll_ball_hint

    def __init__(self, inside=True, visible=True):
        self.inside, self.visible, self.shakes = inside, visible, 0

    def isVisible(self):
        return self.visible

    def _ball_has_something_inside(self):
        return self.inside

    def _shake_ball(self):
        self.shakes += 1


def advance(seconds):
    CLOCK["mono"] += seconds
    CLOCK["wall"] += seconds


def play_out(o, seconds=130, step=1.0):
    for _ in range(int(seconds / step)):
        advance(step)
        o._poll_ball_hint()


def test_about_one_game_in_four_once_10_to_120_s_after():
    saved = deck_confirm.battle_started_at
    random.seed(7)
    try:
        deck_confirm.battle_started_at = lambda: 0.0
        o, delays, games = FakeOverlay(), [], 2000
        for game in range(games):
            o._game_ended_for_ball_hint(game)
            start, before = CLOCK["mono"], o.shakes
            for _ in range(130):
                advance(1.0)
                o._poll_ball_hint()
                if o.shakes > before:
                    delays.append(CLOCK["mono"] - start)
                    break
            play_out(o, 20)
            assert o.shakes - before <= 1  # never twice for one game
        share = len(delays) / games
        assert 0.21 < share < 0.29, share
        assert min(delays) >= 10 and max(delays) <= 121, (min(delays), max(delays))
    finally:
        deck_confirm.battle_started_at = saved


def test_same_game_reported_twice_counts_once():
    random.seed(1)
    o = FakeOverlay()
    o._game_ended_for_ball_hint("b1")
    due = o._ball_hint_at
    o._game_ended_for_ball_hint("b1")
    assert o._ball_hint_at == due


def test_a_new_battle_cancels_it():
    saved = deck_confirm.battle_started_at
    try:
        o = FakeOverlay()
        o._game_ended_for_ball_hint("b2")
        o._ball_hint_at = CLOCK["mono"] + 30  # it was picked
        deck_confirm.battle_started_at = lambda: CLOCK["wall"] + 5  # the next battle begins
        play_out(o, 60)
        assert o.shakes == 0 and o._ball_hint_at is None
    finally:
        deck_confirm.battle_started_at = saved


def test_nothing_inside_or_hidden_means_no_shake():
    saved = deck_confirm.battle_started_at
    try:
        deck_confirm.battle_started_at = lambda: 0.0
        out = FakeOverlay(inside=False)  # buddy is out walking around
        out._game_ended_for_ball_hint("b3")
        out._ball_hint_at = CLOCK["mono"] + 15
        play_out(out, 30)
        assert out.shakes == 0
        hidden = FakeOverlay(visible=False)
        hidden._game_ended_for_ball_hint("b4")
        hidden._ball_hint_at = CLOCK["mono"] + 15
        play_out(hidden, 60)
        hidden.visible = True
        play_out(hidden, 30)
        assert hidden.shakes == 0  # its moment passed while the mini GUI was hidden
    finally:
        deck_confirm.battle_started_at = saved


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
