import base64
import ctypes
import json
import os
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY_FILE = os.path.join(BASE_DIR, ".openai_key")  # legacy plaintext; migrated on first read
API_KEY_SECURE_FILE = os.path.join(BASE_DIR, ".openai_key.dpapi")
USER_CONFIG_FILE = os.path.join(BASE_DIR, ".user_config")
APP_SETTINGS_FILE = os.path.join(BASE_DIR, ".app_settings.json")

DEFAULT_SETTINGS = {
    "local_only_mode": False,
    # Replace both player usernames with placeholders before a battle log is
    # sent to OpenAI (SEC-09). Local parsing always sees the real names.
    "ai_anonymize_names": True,
    # Size for high-resolution screens, in percent (SCALE_MIN..SCALE_MAX): the mini
    # GUI overlay, and the text of every window. Read when the UI starts.
    "hud_scale": 100,
    "text_scale": 100,
}
SCALE_MIN, SCALE_MAX, SCALE_STEP = 80, 200, 5  # Advanced -> HUD size / Text size sliders


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


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data, protect):
    """Encrypt/decrypt bytes with Windows DPAPI (tied to this Windows user)."""
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    func = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not func(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):  # UI_FORBIDDEN
        raise OSError("DPAPI call failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def load_api_key():
    if sys.platform != "win32":
        return _read_text_file(API_KEY_FILE)
    # A plaintext key is newer than the encrypted one (the installer's account
    # page writes it): it wins, and is encrypted and removed right away.
    legacy = _read_text_file(API_KEY_FILE)
    if legacy:
        try:
            save_api_key(legacy)
        except Exception:
            pass
        return legacy
    encoded = _read_text_file(API_KEY_SECURE_FILE)
    if encoded:
        try:
            return _dpapi(base64.b64decode(encoded), False).decode("utf-8").strip() or None
        except Exception:
            pass
    return None


def save_api_key(api_key):
    api_key = (api_key or "").strip()
    if sys.platform != "win32":
        _write_text_file(API_KEY_FILE, api_key)
        return
    if not api_key:
        clear_api_key()
        return
    encoded = base64.b64encode(_dpapi(api_key.encode("utf-8"), True)).decode("ascii")
    _write_text_file(API_KEY_SECURE_FILE, encoded)
    _remove(API_KEY_FILE)


def clear_api_key():
    _remove(API_KEY_FILE)
    _remove(API_KEY_SECURE_FILE)


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


def is_ai_anonymize_names():
    return bool(load_app_settings().get("ai_anonymize_names", True))


def get_scale(key):
    """hud_scale / text_scale as a factor (1.0 = 100 %); bad values mean 1.0."""
    try:
        pct = int(load_app_settings().get(key, 100))
    except (TypeError, ValueError):
        return 1.0
    return pct / 100.0 if SCALE_MIN <= pct <= SCALE_MAX else 1.0
