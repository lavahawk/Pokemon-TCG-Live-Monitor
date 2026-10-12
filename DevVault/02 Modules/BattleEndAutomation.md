---
tags: [module, automation]
file: BattleEndAutomation.py
added: v2.4
---
# BattleEndAutomation.py (v2.4)

A daemon thread started by the monitor once the game process is running.

| State | Trigger | Poll |
|---|---|---|
| In battle | HUD 2/3 anchors | 1.5 s (three 12×12 px grabs) |
| Hot | HUD lost < 3 min ago | BATTLE LOG search every 0.25 s |
| Cold | otherwise | every 1.5 s |
| Disarmed | end screen handled | re-armed by a new HUD or 60 s without the button |

When BATTLE LOG is seen on 2 consecutive frames:
1. A battle log captured since the battle ended → done (the user exported).
2. Wait ≤20 s for the game to be the foreground window, otherwise skip (never click other apps).
3. Launch one ContinueBlocker → click BATTLE LOG → find export (≤6 s, re-click BATTLE LOG once if the popup didn't open) → click export → wait for the monitor's `notify_log_captured()` (≤2.5 s) → retry ≤2 → close the blocker.

Matching: `AutoClicker.find_in_frame` (grayscale, normalized to 540 px window height, multi-scale; scale + location cached in `button_templates/scale_cache.json`).
Logs: `Logs/autoclicker.log`. Toggle: Dashboard → Advanced → "Auto-export…" (`auto_export_battle_log` in `.app_settings.json`).
Test harness: the simulator described in [[Session Log]] (fake mss + scripted end screens).
