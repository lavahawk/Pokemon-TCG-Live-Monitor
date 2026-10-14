import hashlib, os, re, sys, ast, sqlite3
SRC = sys.argv[1]
# Pull pure functions out of the real modules via AST (avoid import side effects)
def load_funcs(path, names):
    tree = ast.parse(open(path, encoding='utf-8').read())
    ns = {'re': re}
    code = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=code, type_ignores=[]), path, 'exec'), ns)
    return ns
p = load_funcs(os.path.join(SRC, 'AIParseBattleLog.py'),
               {'normalize_name','parse_winner_from_log','parse_result_from_log','parse_opponent_from_log'})
m = load_funcs(os.path.join(SRC, 'TCGLiveMonitor.py'), {'is_battle_log'})
USER = open(os.path.join(SRC, '.user_config')).read().strip() if os.path.exists(os.path.join(SRC,'.user_config')) else None
logs = sorted(f for f in os.listdir(os.path.join(SRC,'Logs')) if f.startswith('battle_log_'))
hashes = {}
db = sqlite3.connect(os.path.join(SRC,'tcg_battles.db'))
dbmap = {}
for bid, lf, res in db.execute("select id, log_file, result from battles"):
    dbmap.setdefault(os.path.basename((lf or '').replace('\\','/')), []).append((bid,res))
print(f"username file present: {USER is not None}")
for f in logs:
    txt = open(os.path.join(SRC,'Logs',f), encoding='utf-8', errors='replace').read()
    h = hashlib.sha256(txt.strip().encode()).hexdigest()[:10]
    hashes.setdefault(h, []).append(f)
    winner = p['parse_winner_from_log'](txt)
    last = [l for l in txt.strip().splitlines() if l.strip()][-1][:70]
    print(f"{f[11:30]} hash={h} detect={m['is_battle_log'](txt)} winner={winner!r:18} db={dbmap.get(f)} | last: {last}")
print("\nDUPLICATE CONTENT GROUPS:")
for h, fs in hashes.items():
    if len(fs) > 1:
        print(" ", h, [x[11:30] for x in fs], [dbmap.get(x) for x in fs])
