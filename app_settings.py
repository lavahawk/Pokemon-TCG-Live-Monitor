import json
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY_FILE = os.path.join(BASE_DIR, ".openai_key")
USER_CONFIG_FILE = os.path.join(BASE_DIR, ".user_config")
APP_SETTINGS_FILE = os.path.join(BASE_DIR, ".app_settings.json")

DEFAULT_SETTINGS = {
    "local_only_mode": False,
}


def _read_text_file(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
        return value or None
    except Exception:
        return None


def _write_text_file(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write((value or "").strip())


def load_username():
    return _read_text_file(USER_CONFIG_FILE)


def save_username(username):
    _write_text_file(USER_CONFIG_FILE, username or "")


def load_api_key():
    return _read_text_file(API_KEY_FILE)


def save_api_key(api_key):
    _write_text_file(API_KEY_FILE, api_key or "")


def clear_api_key():
    try:
        if os.path.exists(API_KEY_FILE):
            os.remove(API_KEY_FILE)
    except Exception:
        pass


def load_app_settings():
    settings = dict(DEFAULT_SETTINGS)
    if not os.path.exists(APP_SETTINGS_FILE):
        return settings
    try:
        with open(APP_SETTINGS_FILE, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            settings.update(loaded)
    except Exception:
        pass
    return settings


def save_app_settings(settings):
    payload = dict(DEFAULT_SETTINGS)
    if isinstance(settings, dict):
        payload.update(settings)
    with open(APP_SETTINGS_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def is_local_only_mode():
    return bool(load_app_settings().get("local_only_mode", False))
