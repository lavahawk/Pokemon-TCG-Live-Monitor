"""Reproduction harness for findings. Run from a COPY of the app folder (cwd)."""
import sys, os, types, json, sqlite3, shutil, traceback
sys.path.insert(0, '/home/claude/stubs'); import winstubs  # noqa
sys.modules['startup_utils'] = types.ModuleType('startup_utils')
sys.path.insert(0, os.getcwd())
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
results = {}
def case(name):
    def deco(fn):
        try:
            results[name] = fn()
        except Exception as e:
            results[name] = f"EXCEPTION {type(e).__name__}: {e}"
        return fn
    return deco

import AIParseBattleLog as P
log = open('Logs/battle_log_2026-09-13_21-48-12.txt', encoding='utf-8', errors='replace').read()

@case("P1 local_fallback_parse when user types opponent deck")
def _():
    P._console_available = lambda: True
    P.prompt_string = lambda *a, **k: "Dragapult"
    return P.local_fallback_parse(log, "22lava44")

@case("P3 winner regex: username with a dot")
def _():
    t = "Setup\n...\nAll Prize cards taken. lava.44 wins."
    return {"winner": P.parse_winner_from_log(t), "result_for_lava.44": P.parse_result_from_log(t, "lava.44")}

@case("P2 is_tournament_battle referenced outside its def")
def _():
    src = open('AIParseBattleLog.py', encoding='utf-8').read()
    return src.count("is_tournament_battle(")

import BattleDatabase as BD
tmpdb = '/tmp/claude-0/repro.db'; shutil.copy('tcg_battles.db', tmpdb)
db = BD.BattleDatabase(tmpdb)

@case("D3 get_all_time_stats vs real totals")
def _():
    c = sqlite3.connect(tmpdb)
    real = c.execute("select count(*), sum(result='Win'), sum(result='Loss') from battles").fetchone()
    return {"get_all_time_stats": db.get_all_time_stats()[:3], "actual": real}

@case("D1 rebuild_session_stats moves evening games to next UTC day")
def _():
    c = sqlite3.connect(tmpdb)
    before = c.execute("select date,wins,losses from session_stats order by date").fetchall()
    db.rebuild_session_stats()
    after = c.execute("select date,wins,losses from session_stats order by date").fetchall()
    return {"before": before, "after": after}

import deck_analytics as A
@case("A1 rank_weight on the user's actual rank range")
def _():
    return {r: round(A.rank_weight(r), 3) for r in (30, 100, 168, 260)}

@case("A1b rank-weighted summary for main deck")
def _():
    s = A.rank_weighted_winrate(db.get_deck_battles_with_rank('Pult Hammers NAIC 2026'))
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items() if k in ('games','wins','losses','weighted_winrate','effective_n','confidence_label')}

import japan_data as J
@case("J3 substring translation picks first key, not longest")
def _():
    return {jp: J.translate_deck_name(jp) for jp in ["バシャーモex＋ドラパルトex", "メガゲッコウガデッキ", "シロナのガブリアス", "ガブリアス", "ドデカバシ", "カミツオロチ", "イワパレス"]}

@case("J2 Japan rows show 100% win rate")
def _():
    rows = J._consolidate_rows([{"deck_jp": "ドラパルト", "count": 5}], lambda s: J.translate_deck_name(s))
    r = rows[0]; return {k: r[k] for k in ("deck","wins","losses","win_pct","bayes_win_pct")}

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import StatsUI as S

@case("S1 LimitlessDashboardManager attributes after __init__")
def _():
    m = S.LimitlessDashboardManager(app)
    out = {a: hasattr(m, a) for a in ("delayed_poll_timer", "chat_poll_timer")}
    try:
        m.background_page = types.SimpleNamespace(url=lambda: types.SimpleNamespace(toString=lambda: "https://play.limitlesstcg.com/dashboard"))
        m._on_background_load_finished(True)
        out["_on_background_load_finished"] = "ok"
    except Exception as e:
        out["_on_background_load_finished"] = f"{type(e).__name__}: {e}"
    try:
        m._on_chat_page_load_finished(True); out["_on_chat_page_load_finished"] = "ok"
    except Exception as e:
        out["_on_chat_page_load_finished"] = f"{type(e).__name__}: {e}"
    return out

for k, v in results.items():
    print(f"\n### {k}\n{json.dumps(v, ensure_ascii=False, indent=1, default=str) if not isinstance(v, str) else v}")
