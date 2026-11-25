"""Replay timeline: which action lines are highlights, turns, jumps."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from replay_timeline import classify, parse_actions  # noqa: E402

ACTIONS = [
    (9, "Turn 1 - Setoplays's Turn"),
    (11, "Mega Kangaskhan ex used Run Errand Drew 2 cards"),
    (14, "Turn 2 - 22lava44's Turn"),
    (37, "22lava44 evolved Dunsparce into Dudunsparce"),
    (42, "22lava44 played Rare Candy Evolved Gastly into Gengar ex"),
    (59, "Crustle used Superb Scissors on Dudunsparce for 120 damage"),
    (84, "Gengar ex used Chaotic Pain +130 damage counters on Setoplays's Mega Kangaskhan ex"),
    (103, "Mega Kangaskhan ex was Knocked Out!"),
    (104, "22lava44 took 3 Prize card(s) Added to hand: Nighttime Mine"),
]


def test_classify():
    kinds = {n: classify(t) for n, t in ACTIONS}
    assert kinds[11] is None            # an ability, no damage
    assert kinds[37] == kinds[42] == "evolve"
    assert kinds[59] == kinds[84] == "attack"
    assert kinds[103] == "ko"
    assert kinds[104] == "prize"


def test_turns_and_events():
    parsed = parse_actions(ACTIONS)
    assert parsed["turns"] == [(9, 1, "Setoplays"), (14, 2, "22lava44")]
    assert [n for n, _k, _t in parsed["events"]] == [37, 42, 59, 84, 103, 104]


def test_highlight_jumps():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from replay_timeline import ReplayTimeline
    tl = ReplayTimeline()
    tl.set_actions(ACTIONS, me="22lava44")
    tl.set_position(60, 225)
    assert tl.next_highlight(1) == 84
    assert tl.next_highlight(-1) == 59
    tl.set_position(104, 225)
    assert tl.next_highlight(1) is None
    seen = []
    tl.seek.connect(seen.append)
    tl._step(1)
    tl._jump(-1)
    assert seen == [105, 103]
    assert "Action 104" in tl.now.text()
    app.processEvents()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
