"""Tests for datatransfer.py (run: python test_datatransfer.py). Everything
happens in temp folders."""
import atexit
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import datatransfer as T

TMP = tempfile.mkdtemp(prefix="datatransfer_test_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)


def make_app(name, battles=3):
    base = os.path.join(TMP, name)
    os.makedirs(os.path.join(base, "Logs"), exist_ok=True)
    os.makedirs(os.path.join(base, "button_templates"), exist_ok=True)
    conn = sqlite3.connect(os.path.join(base, T.DB_NAME))
    conn.execute("CREATE TABLE battles (id INTEGER PRIMARY KEY, opponent_deck TEXT, log_file TEXT)")
    conn.executemany("INSERT INTO battles (opponent_deck, log_file) VALUES (?, ?)",
                     [(f"Deck {i}", os.path.join(base, "Logs", "battle_log_1.txt")) for i in range(battles)])
    conn.commit()
    conn.close()
    with open(os.path.join(base, ".app_settings.json"), "w") as f:
        json.dump({"tie_mode": "loss"}, f)
    with open(os.path.join(base, ".openai_key.dpapi"), "w") as f:
        f.write("ENCRYPTED")
    with open(os.path.join(base, "Logs", "battle_log_1.txt"), "w") as f:
        f.write("Turn # 1")
    with open(os.path.join(base, "Logs", "monitor.log"), "w") as f:
        f.write("noise")
    with open(os.path.join(base, "button_templates", "battle_log.png"), "wb") as f:
        f.write(b"png")
    return base


def test_round_trip_to_a_new_pc():
    old = make_app("old_pc", battles=5)
    new = make_app("new_pc", battles=1)
    zip_path = os.path.join(TMP, "backup.zip")
    result = T.export_data(zip_path, base_dir=old)
    assert result["battles"] == 5 and result["logs"] == 1
    names = zipfile.ZipFile(zip_path).namelist()
    assert ".openai_key.dpapi" not in names and "Logs/monitor.log" not in names  # key and noise stay out
    restored = T.import_data(zip_path, base_dir=new)
    conn = sqlite3.connect(os.path.join(new, T.DB_NAME))
    assert conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0] == 5
    conn.close()
    assert json.load(open(os.path.join(new, ".app_settings.json")))["tie_mode"] == "loss"
    shutil.rmtree(old)  # the old PC is gone: logs must point into the new copy
    T.relink_logs(new)
    conn = sqlite3.connect(os.path.join(new, T.DB_NAME))
    paths = {r[0] for r in conn.execute("SELECT log_file FROM battles")}
    conn.close()
    assert paths == {os.path.join(new, "Logs", "battle_log_1.txt")}
    assert open(os.path.join(new, ".openai_key.dpapi")).read() == "ENCRYPTED"  # new PC's key untouched
    # the data that was there before is kept in Backups\\pre-import-*
    conn = sqlite3.connect(os.path.join(restored["backup"], T.DB_NAME))
    assert conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0] == 1
    conn.close()


def test_import_rejects_foreign_zip_and_unsafe_paths():
    bad = os.path.join(TMP, "bad.zip")
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("hello.txt", "x")
    try:
        T.import_data(bad, base_dir=make_app("victim"))
        raise AssertionError("a zip without our manifest must be refused")
    except ValueError:
        pass
    evil = os.path.join(TMP, "evil.zip")
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr(T.MANIFEST, json.dumps({"battles": 0}))
        z.writestr("../outside.txt", "x")
        z.writestr("Logs/../../outside2.txt", "x")
        z.writestr("StatsUI.py", "print('replaced code')")
    target = make_app("victim2")
    T.import_data(evil, base_dir=target)
    assert not os.path.exists(os.path.join(TMP, "outside.txt"))
    assert not os.path.exists(os.path.join(TMP, "outside2.txt"))
    assert not os.path.exists(os.path.join(target, "StatsUI.py"))  # only data files are restored


def test_backups_are_pruned():
    base = make_app("pruned")
    for _ in range(T.KEEP_BACKUPS + 2):
        T.backup_now("pre-update", base_dir=base)
        T._stamp = (lambda counter=[0]: (counter.__setitem__(0, counter[0] + 1), f"t{counter[0]:03d}")[1])
    kept = [d for d in os.listdir(os.path.join(base, "Backups")) if d.startswith("pre-update-")]
    assert len(kept) <= T.KEEP_BACKUPS
    assert any(os.path.exists(os.path.join(base, "Backups", d, ".openai_key.dpapi")) for d in kept)


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
