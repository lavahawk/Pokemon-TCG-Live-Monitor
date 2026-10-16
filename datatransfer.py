"""
Your data in one .zip: back it up, move it to another PC, restore it.

  export_data(path)   battles (a consistent SQLite copy), settings, decklists,
                      deck archetypes, HUD buddy, window layout, screen
                      calibration, captured buttons and the battle logs
  import_data(path)   restores such a zip; what's there now is first copied
                      to Backups\\pre-import-<time>\\
  backup_now(label)   the same copy for the updater (Backups\\pre-update-*)
  cloud_folders()     synced Google Drive / Box / OneDrive / Dropbox folders,
                      to save the zip straight into

Not included: the OpenAI key (encrypted for this Windows account only, so it
can't be read on another PC - enter it again there), caches, website sign-ins.
"""

import datetime as _dt
import json
import os
import shutil
import sqlite3
import zipfile

from version import APP_VERSION

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = "tcg_battles.db"
DATA_FILES = (".app_settings.json", ".user_config", ".decklists.json", ".deck_archetypes.json",
              ".pet_state.json", ".stats_window_geometry.json", "screen_regions.json", ".last_deck")
DATA_DIRS = ("button_templates",)
LOG_PATTERN = ("battle_log_", ".txt")
MANIFEST = "ptcgl_monitor_backup.json"
KEEP_BACKUPS = 5


def _stamp():
    return _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _copy_db(src, dst):
    """A consistent copy even while the app is writing (SQLite backup API)."""
    source = sqlite3.connect(src)
    try:
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _items(base_dir):
    """(relative path, absolute path) of every data file that exists."""
    out = []
    for name in DATA_FILES:
        path = os.path.join(base_dir, name)
        if os.path.isfile(path):
            out.append((name, path))
    for folder in DATA_DIRS:
        root = os.path.join(base_dir, folder)
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f == "scale_cache.json":
                    continue
                full = os.path.join(dirpath, f)
                out.append((os.path.relpath(full, base_dir).replace("\\", "/"), full))
    logs = os.path.join(base_dir, "Logs")
    if os.path.isdir(logs):
        for f in sorted(os.listdir(logs)):
            if f.startswith(LOG_PATTERN[0]) and f.endswith(LOG_PATTERN[1]):
                out.append((f"Logs/{f}", os.path.join(logs, f)))
    return out


def export_data(path, base_dir=BASE_DIR):
    """Write the backup zip. Returns {"path", "battles", "files", "logs"}."""
    tmp_db = os.path.join(base_dir, f".export_{os.getpid()}.db")
    battles = 0
    items = _items(base_dir)
    db = os.path.join(base_dir, DB_NAME)
    has_db = os.path.isfile(db)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    try:
        if has_db:
            _copy_db(db, tmp_db)
            conn = sqlite3.connect(tmp_db)
            try:
                battles = conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0]
            except sqlite3.Error:
                battles = 0
            finally:
                conn.close()
        manifest = {"app": "Pokemon TCG Live Monitor", "version": APP_VERSION,
                    "created": _dt.datetime.now().isoformat(timespec="seconds"), "battles": battles,
                    "files": [rel for rel, _ in items] + ([DB_NAME] if has_db else [])}
        with zipfile.ZipFile(path + ".part", "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFEST, json.dumps(manifest, indent=2))
            if has_db:
                z.write(tmp_db, DB_NAME)
            for rel, full in items:
                z.write(full, rel)
        os.replace(path + ".part", path)
    finally:
        if os.path.exists(tmp_db):
            os.remove(tmp_db)
    return {"path": path, "battles": battles, "files": len(items) + (1 if has_db else 0),
            "logs": sum(1 for rel, _ in items if rel.startswith("Logs/"))}


def read_manifest(path):
    """The backup's manifest dict, or raise ValueError if it isn't one of ours."""
    try:
        with zipfile.ZipFile(path) as z:
            return json.loads(z.read(MANIFEST).decode("utf-8"))
    except (KeyError, zipfile.BadZipFile, ValueError, OSError) as exc:
        raise ValueError("That file isn't a Pokemon TCG Live Monitor backup.") from exc


def backup_now(label, base_dir=BASE_DIR):
    """Copy the current data to Backups\\<label>-<time>\\ (keeps the newest few)."""
    root = os.path.join(base_dir, "Backups")
    target = os.path.join(root, f"{label}-{_stamp()}")
    os.makedirs(target, exist_ok=True)
    db = os.path.join(base_dir, DB_NAME)
    if os.path.isfile(db):
        _copy_db(db, os.path.join(target, DB_NAME))
    for name in DATA_FILES + (".openai_key.dpapi",):
        src = os.path.join(base_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(target, name))
    for folder in DATA_DIRS:
        src = os.path.join(base_dir, folder)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(target, folder), dirs_exist_ok=True)
    old = sorted(d for d in os.listdir(root) if d.startswith(label + "-"))
    for name in old[:-KEEP_BACKUPS]:
        shutil.rmtree(os.path.join(root, name), ignore_errors=True)
    return target


def import_data(path, base_dir=BASE_DIR):
    """Restore a backup zip over this copy's data. The current data is saved
    first (backup_now("pre-import")). Returns {"battles", "files", "backup"}."""
    manifest = read_manifest(path)
    safety = backup_now("pre-import", base_dir)
    restored = 0
    base = os.path.realpath(base_dir)
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name = info.filename
            if name == MANIFEST or name.endswith("/"):
                continue
            allowed = (name == DB_NAME or name in DATA_FILES
                       or any(name.startswith(d + "/") for d in DATA_DIRS)
                       or (name.startswith("Logs/") and name.endswith(".txt") and "/" not in name[5:]))
            target = os.path.realpath(os.path.join(base_dir, name))
            if not allowed or not target.startswith(base + os.sep):
                continue  # only known data files, never outside the app folder
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target + ".import", "wb") as dst:
                shutil.copyfileobj(src, dst)
            os.replace(target + ".import", target)
            restored += 1
    relink_logs(base_dir)
    return {"battles": manifest.get("battles", 0), "files": restored, "backup": safety,
            "from_version": manifest.get("version")}


def relink_logs(base_dir=BASE_DIR):
    """Battles store their log by full path; after a move to another PC (or
    folder) point them at this copy's Logs\ when the file is there."""
    db = os.path.join(base_dir, DB_NAME)
    logs = os.path.join(base_dir, "Logs")
    if not os.path.isfile(db) or not os.path.isdir(logs):
        return 0
    conn = sqlite3.connect(db)
    changed = 0
    try:
        rows = conn.execute("SELECT id, log_file FROM battles WHERE log_file IS NOT NULL AND log_file != ''").fetchall()
        for battle_id, log_file in rows:
            if os.path.exists(log_file):
                continue
            local = os.path.join(logs, os.path.basename(str(log_file).replace("\\", "/")))
            if os.path.exists(local):
                conn.execute("UPDATE battles SET log_file = ? WHERE id = ?", (local, battle_id))
                changed += 1
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return changed


def default_export_name():
    return f"PTCGL-Monitor-backup-{_dt.date.today().isoformat()}.zip"


def cloud_folders():
    """[(label, folder)] of synced cloud folders found on this PC."""
    home = os.path.expanduser("~")
    found, seen = [], set()

    def add(label, path):
        if path and os.path.isdir(path) and os.path.realpath(path).lower() not in seen:
            seen.add(os.path.realpath(path).lower())
            found.append((label, path))

    for drive in "GHIJKLMNOPQRSTUVWXYZ":
        add("Google Drive", f"{drive}:\\My Drive")
    add("Google Drive", os.path.join(home, "Google Drive", "My Drive"))
    add("Google Drive", os.path.join(home, "Google Drive"))
    add("Google Drive", os.path.join(home, "My Drive"))
    add("Box", os.path.join(home, "Box"))
    add("Box", os.path.join(home, "Box Sync"))
    add("OneDrive", os.environ.get("OneDrive"))
    add("OneDrive", os.path.join(home, "OneDrive"))
    add("Dropbox", os.path.join(home, "Dropbox"))
    return found


CLOUD_UPLOAD_PAGES = (("Google Drive", "https://drive.google.com/drive/my-drive"),
                      ("Box", "https://app.box.com/folder/0"))
