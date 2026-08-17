"""Validation tests for the rank-weighted Elo win rate model + tournament weighting."""
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deck_analytics import rank_weight, rank_weighted_winrate, wilson_interval, TOURNAMENT_WEIGHT

print("=" * 70)
print("RANK-WEIGHTED WINRATE + TOURNAMENT VALIDATION")
print("=" * 70)

# --- Test 1: Weight anchors match the user's described Elo ladder ---
print()
print("[1] Elo weight anchors")
anchors = [
    (1200, "below Masterball (heavy penalty)"),
    (1500, "Masterball / average"),
    (1600, "above average"),
    (1700, "serious"),
    (1800, "pro"),
    (1900, "top pro"),
]
for elo, label in anchors:
    w = rank_weight(elo)
    print("  Elo %4d (%s) weight = %.3f" % (elo, label, w))

# --- Test 2: Tournament weight bypasses rank penalty ---
print()
print("[2] Tournament games get huge weight regardless of rank")
for elo in [1200, 1500, 1800]:
    w = rank_weight(elo, is_tournament=True)
    print("  tournament @ %d: weight = %.1f (expect %.1f)" % (elo, w, TOURNAMENT_WEIGHT))

# --- Test 3: Same 10-0 record, different ranks -> CI width shrinks as rank rises ---
print()
print("[3] Same 10-0 record, different ranks -> CI width should shrink as rank rises")
for elo in [1200, 1500, 1700, 1900]:
    s = rank_weighted_winrate([{"result": "Win", "my_rank": elo} for _ in range(10)])
    print(
        "  10-0 @ %d: eff_n=%.1f, CI=[%.2f,%.2f], width=%.2f"
        % (elo, s["effective_n"], s["ci_low"], s["ci_high"], s["interval_width"])
    )

# --- Test 4: Tournament games dominate the estimate ---
print()
print("[4] A few tournament wins should carry more weight than many low-rank ladder wins")
b = [{"result": "Win", "my_rank": 1200, "is_tournament": True} for _ in range(5)]
s = rank_weighted_winrate(b)
print("  5 tournament wins: eff_n=%.1f, CI=[%.2f,%.2f]" % (s["effective_n"], s["ci_low"], s["ci_high"]))
print("  tournament_games=%d, tournament_wins=%d" % (s["tournament_games"], s["tournament_wins"]))

# --- Test 5: Mixed tournament + ladder ---
print()
print("[5] Mixed: 3 tournament wins + 7 ladder wins @ 1500 + 2 ladder losses @ 1500")
b = [{"result": "Win", "my_rank": 1500, "is_tournament": True} for _ in range(3)]
b += [{"result": "Win", "my_rank": 1500} for _ in range(7)]
b += [{"result": "Loss", "my_rank": 1500} for _ in range(2)]
s = rank_weighted_winrate(b)
print("  games=%d, weighted_winrate=%.1f%%, eff_n=%.1f" % (s["games"], s["weighted_winrate"] * 100, s["effective_n"]))
print("  tournament_games=%d, tournament_wins=%d" % (s["tournament_games"], s["tournament_wins"]))

# --- Test 6: 50/50 at any rank should give ~50% ---
print()
print("[6] 5-5 at various ranks -> winrate ~0.5")
for elo in [1200, 1500, 1800]:
    b = [{"result": "Win", "my_rank": elo} for _ in range(5)] + [
        {"result": "Loss", "my_rank": elo} for _ in range(5)
    ]
    s = rank_weighted_winrate(b)
    print("  5-5 @ %d: winrate=%.3f" % (elo, s["weighted_winrate"]))

# --- Test 7: Ties handled correctly ---
print()
print("[7] Ties count as 1/3 win")
b = [
    {"result": "Win", "my_rank": 1700},
    {"result": "Tie", "my_rank": 1700},
    {"result": "Loss", "my_rank": 1700},
]
s = rank_weighted_winrate(b)
print("  W/T/L @1700: weighted_winrate=%.3f (expect ~0.444)" % s["weighted_winrate"])

# --- Test 8: No rank data -> neutral weight, still works ---
print()
print("[8] No rank data (my_rank=None)")
b = [{"result": "Win", "my_rank": None} for _ in range(6)] + [
    {"result": "Loss", "my_rank": None} for _ in range(4)
]
s = rank_weighted_winrate(b)
print(
    "  6-4 no rank: winrate=%.3f, eff_n=%.1f, coverage=%.0f%%"
    % (s["weighted_winrate"], s["effective_n"], s["rank_coverage"] * 100.0)
)

# --- Test 9: Wilson interval known values ---
print()
print("[9] Wilson interval known benchmarks")
lo, hi = wilson_interval(80, 100)
print("  80/100: [%.3f,%.3f] (expect ~[0.711,0.867])" % (lo, hi))
lo, hi = wilson_interval(50, 100)
print("  50/100: [%.3f,%.3f] (expect ~[0.403,0.597])" % (lo, hi))
lo, hi = wilson_interval(0, 10)
print("  0/10:   [%.3f,%.3f] (expect ~[0.0,0.278])" % (lo, hi))

print()
print("ALL VALIDATION CHECKS COMPLETE")
