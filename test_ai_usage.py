"""Tests for ai_usage.py (run: python test_ai_usage.py). The ledger lives in a
temp file; dates are passed in."""
import atexit
import datetime as dt
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ai_usage as U

TMP = tempfile.mkdtemp(prefix="ai_usage_test_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
U.USAGE_FILE = os.path.join(TMP, ".ai_usage.json")
DAY = dt.datetime(2026, 10, 16, 12, 0)


def reset():
    if os.path.exists(U.USAGE_FILE):
        os.remove(U.USAGE_FILE)


def test_model_order_has_no_gpt4o():
    assert U.MODEL_ORDER == ["gpt-5.4-nano-2026-03-17", "gpt-4.1-nano", "gpt-4.1-mini"]


def test_call_cost_uses_real_prices():
    # 4,400 in + 150 out on gpt-5.4-nano: 4400*0.20 + 150*1.25 per 1M
    assert abs(U.call_cost("gpt-5.4-nano-2026-03-17", 4400, 150) - 0.0010675) < 1e-9
    assert U.call_cost("gpt-4.1-nano", 1000, 0, cached_tokens=1000) < U.call_cost("gpt-4.1-nano", 1000, 0)


def test_light_model_first_after_40_games_today():
    reset()
    for _ in range(U.DAILY_FULL_GAMES - 1):
        U.record("gpt-5.4-nano-2026-03-17", 4000, 150, now=DAY)
    assert U.models_for_now(now=DAY)[0] == "gpt-5.4-nano-2026-03-17"
    U.record("gpt-5.4-nano-2026-03-17", 4000, 150, now=DAY)
    assert U.models_for_now(now=DAY) == ["gpt-4.1-nano", "gpt-4.1-mini"]
    assert U.models_for_now(now=DAY + dt.timedelta(days=1))[0] == "gpt-5.4-nano-2026-03-17"  # new day


def test_budget_stops_ai_and_resets_next_month():
    reset()
    assert not U.over_budget(now=DAY)
    while not U.over_budget(now=DAY):
        U.record("gpt-4.1-mini", 100_000, 10_000, now=DAY)  # $0.056 each
    assert U.budget_left(now=DAY) == 0.0
    assert U.next_reset(now=DAY) == dt.date(2026, 11, 1)
    assert not U.over_budget(now=dt.datetime(2026, 11, 1, 0, 1))
    assert U.next_reset(now=dt.datetime(2026, 12, 5)) == dt.date(2027, 1, 1)


def test_corrupt_ledger_is_treated_as_empty():
    with open(U.USAGE_FILE, "w") as handle:
        handle.write("not json")
    assert U.usage(now=DAY)["spent_usd"] == 0.0


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
