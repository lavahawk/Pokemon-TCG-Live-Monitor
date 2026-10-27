"""meta_trend: Meta -> Trend from the sheet's cached events (no network)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import meta_trend as M
import trainerhill_trend as T

SHEET = {
    "trend_events": [
        {"d": "2026-10-01", "k": "online", "p": 64, "c": {"dragapult": 20, "gengar": 10, "other": 34}},
        {"d": "2026-10-01", "k": "online", "p": 40, "c": {"dragapult": 10, "gengar": 10, "other": 20}},
        {"d": "2026-10-02", "k": "in_person", "p": 900, "c": {"dragapult": 100, "gengar": 50, "other": 750}},
        {"d": "2026-10-03", "k": "online", "p": 16, "c": {"gengar": 16}},
    ],
    "trend_names": {"dragapult": ["Dragapult", ["dragapult"]], "gengar": ["Gengar", ["gengar"]]},
}


def test_old_trainerhill_source_names_still_work():
    assert M.source_keys(["play", "labs"]) == ["online", "in_person"]
    assert M.source_keys(["online", "play", "bogus"]) == ["online"]


def test_breakdown_counts_players_and_filters():
    b = M.breakdown(SHEET, "2026-10-01", ["online", "in_person"], min_players=32)
    assert b["total_events"] == 3  # the 16-player event is too small
    top = b["archetypes"][0]
    assert top["id"] == "other" and top["count"] == 804
    drag = next(a for a in b["archetypes"] if a["id"] == "dragapult")
    assert drag["name"] == "Dragapult" and drag["icons"] == ["dragapult"]
    assert abs(drag["percentage"] - 130 / b["total_players"]) < 1e-9
    online = M.breakdown(SHEET, "2026-10-02", ["online"])
    assert online["total_events"] == 1 and online["archetypes"][0]["id"] == "gengar"


def test_trend_sums_days_for_the_chosen_decks_only():
    t = M.trend(SHEET, "2026-10-01", ["online", "in_person"], ["dragapult", "gengar"])
    assert [d["date"] for d in t["daily_trend"]] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    first = {d["deck_id"]: d["count"] for d in t["daily_trend"][0]["decks"]}
    assert first == {"dragapult": 30, "gengar": 20}
    dates, series = T.series(t, ["dragapult", "gengar"])
    assert series["dragapult"][1][0] == 60.0  # share among the chosen decks that day
    assert series["gengar"][1][2] == 100.0


def test_movers_split_rising_and_falling():
    summary = {"a": {"trend": 2.5}, "b": {"trend": -1.8}, "c": {"trend": 0.4}, "d": {"trend": 4.0}}
    rising, falling = M.movers(summary, {"a": "A", "b": "B", "d": "D"})
    assert rising == [("D", 4.0), ("A", 2.5)]
    assert falling == [("B", -1.8)]


def test_empty_sheet_is_empty_not_an_error():
    assert M.breakdown(None, "2026-01-01", ["online"])["archetypes"] == []
    assert M.trend({}, "2026-01-01", ["online"], ["x"])["daily_trend"] == []


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
