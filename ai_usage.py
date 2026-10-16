"""
AI usage ledger: what the OpenAI calls cost, and the limits that follow.

  record()          one call's real token counts (completion.usage) -> USD at
                    the model's price, added to this month and today
  models_for_now()  the model order for the next battle: the full order, or
                    the light model first after DAILY_FULL_GAMES AI games today
  budget_left()     USD left this month; at 0 the parser switches to manual
                    mode (manual_reason "ai_budget") until the next month

Stored in .ai_usage.json next to the app (per PC; not part of data export).
"""

import datetime as _dt
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USAGE_FILE = os.path.join(BASE_DIR, ".ai_usage.json")

PRIMARY_MODEL = "gpt-5.4-nano-2026-03-17"
LIGHT_MODEL = "gpt-4.1-nano"
MODEL_ORDER = [PRIMARY_MODEL, LIGHT_MODEL, "gpt-4.1-mini"]
DAILY_FULL_GAMES = 40          # AI games per day on the primary model; then the light model leads
MONTHLY_BUDGET_USD = 2.50      # AI spend per calendar month; then manual mode

# USD per 1M tokens (input, cached input, output); OpenAI standard tier, 2026-10-16.
PRICES = {
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "gpt-4.1-nano": (0.10, 0.025, 0.40),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
}
FALLBACK_PRICE = (0.40, 0.10, 1.60)  # an unknown model is costed like the dearest one we use


def _price(model):
    for prefix, price in PRICES.items():
        if str(model or "").startswith(prefix):
            return price
    return FALLBACK_PRICE


def call_cost(model, prompt_tokens, completion_tokens, cached_tokens=0):
    """USD for one call (completion tokens include any reasoning tokens)."""
    inp, cached, out = _price(model)
    cached_tokens = max(0, min(int(cached_tokens or 0), int(prompt_tokens or 0)))
    fresh = max(0, int(prompt_tokens or 0) - cached_tokens)
    return (fresh * inp + cached_tokens * cached + int(completion_tokens or 0) * out) / 1_000_000


def _now():
    return _dt.datetime.now()


def _load():
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    tmp = USAGE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(tmp, USAGE_FILE)
    except OSError:
        pass


def _current(data, now=None):
    """The ledger with stale month/day counters reset."""
    now = now or _now()
    month, day = now.strftime("%Y-%m"), now.strftime("%Y-%m-%d")
    if data.get("month") != month:
        data.update(month=month, spent_usd=0.0, calls=0)
    if data.get("day") != day:
        data.update(day=day, games_today=0)
    return data


def record(model, prompt_tokens, completion_tokens, cached_tokens=0, now=None):
    """Add one AI-parsed game. Returns its cost in USD."""
    cost = call_cost(model, prompt_tokens, completion_tokens, cached_tokens)
    data = _current(_load(), now)
    data["spent_usd"] = round(float(data.get("spent_usd") or 0.0) + cost, 6)
    data["calls"] = int(data.get("calls") or 0) + 1
    data["games_today"] = int(data.get("games_today") or 0) + 1
    _save(data)
    return cost


def usage(now=None):
    data = _current(_load(), now)
    return {"month": data["month"], "spent_usd": float(data.get("spent_usd") or 0.0),
            "calls": int(data.get("calls") or 0), "games_today": int(data.get("games_today") or 0)}


def budget_left(now=None):
    return max(0.0, MONTHLY_BUDGET_USD - usage(now)["spent_usd"])


def over_budget(now=None):
    return budget_left(now) <= 0.0


def models_for_now(now=None):
    """After DAILY_FULL_GAMES AI games today the light model goes first."""
    if usage(now)["games_today"] >= DAILY_FULL_GAMES:
        return [LIGHT_MODEL] + [m for m in MODEL_ORDER if m not in (LIGHT_MODEL, PRIMARY_MODEL)]
    return list(MODEL_ORDER)


def next_reset(now=None):
    """First day of next month (when the budget starts over)."""
    now = now or _now()
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return _dt.date(year, month, 1)
