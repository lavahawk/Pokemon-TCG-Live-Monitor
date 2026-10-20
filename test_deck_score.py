"""deck_score: strength from pairings only, personal priors (no network, no DB)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deck_analytics

deck_analytics.tie_mode = lambda: "half"  # pin the tie rule: the user's settings must not matter

import deck_score as S


def _sheet(phantom_losses=0.0):
    """Four archetypes with symmetric pairings; `phantom_losses` adds
    standings-only losses (no-shows, drops) to every row."""
    ids = ["a", "b", "c", "d"]
    rate = {("a", "b"): 0.6, ("a", "c"): 0.55, ("a", "d"): 0.5, ("b", "c"): 0.5, ("b", "d"): 0.45, ("c", "d"): 0.5}
    games = 400.0
    rows = []
    for i in ids:
        matchups = {i: [games / 2, games / 2, 0]}  # mirror
        for j in ids:
            if i == j:
                continue
            p = rate.get((i, j), 1.0 - rate.get((j, i), 0.5))
            matchups[j] = [games * p, games * (1 - p), 0]
        w = sum(v[0] for v in matchups.values())
        l = sum(v[1] for v in matchups.values()) + phantom_losses
        rows.append({"id": i, "deck": i.upper(), "share_en": 25.0, "wins": w, "losses": l, "ties": 0,
                     "eff_games": w + l, "raw_games": w + l, "matchups": matchups})
    return rows


def test_standings_only_losses_do_not_move_strength():
    clean, _ = S.compute_scores(_sheet())
    noisy, _ = S.compute_scores(_sheet(phantom_losses=900.0))
    for key in "abcd":
        assert abs(clean[key]["strength"] - noisy[key]["strength"]) < 0.005, key
        assert abs(clean[key]["score"] - noisy[key]["score"]) < 0.005, key


def test_field_average_score_is_par():
    res, info = S.compute_scores(_sheet())
    mean = sum(res[k]["score"] for k in "abcd") / 4
    assert abs(mean - info["par"]) < 0.01, mean


def test_zero_game_version_scores_like_its_archetype():
    mine = [{"id": "you:A", "deck": "My A", "wins": 0.0, "losses": 0.0, "ties": 0, "matchups": {},
             "ladder_frac": 1.0, "mirror_id": "a"},
            {"id": "you:X", "deck": "Rogue", "wins": 0.0, "losses": 0.0, "ties": 0, "matchups": {},
             "ladder_frac": 1.0, "mirror_id": None}]
    res, info = S.compute_scores(_sheet(), mine)
    assert abs(res["you:A"]["score"] - res["a"]["score"]) < 0.005
    assert abs(res["you:X"]["score"] - info["par"]) < 0.005
    assert abs(res["you:X"]["own"]["score"] - info["par"]) < 0.005


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
