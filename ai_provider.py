"""
Where AI deck detection runs (setting "ai_provider"):

  hosted      the AI edition's proxy (edition.HOSTED_AI_URL). The OpenAI key
              stays on the server; this PC only keeps a per-install token
              (DPAPI-encrypted, .ai_install.dpapi) that the server can revoke.
  openai      the user's own OpenAI key (app_settings.load_api_key).
  compatible  any OpenAI-compatible server: a local model (Ollama, LM Studio)
              or another provider (OpenRouter, Groq...): base URL, model, key.
  none        no AI: the local predictor, the overlay asks after each battle.
  auto        (default) own key if one is saved, else hosted when this
              edition has it, else none.

resolve() turns the setting into a Plan the parser uses; a Plan without a
client carries the manual_reason the overlay shows.
"""

import base64
import json
import os
import re
import ssl
import sys
import types
import urllib.error
import urllib.request

import ai_usage
import app_settings
import edition

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTALL_TOKEN_FILE = os.path.join(BASE_DIR, ".ai_install.dpapi")
COMPAT_KEY_FILE = os.path.join(BASE_DIR, ".ai_compat_key.dpapi")
COMPAT_KEY_PLAIN = os.path.join(BASE_DIR, ".ai_compat_key")      # installer page; migrated on first read
INSTALLER_CHOICE_FILE = os.path.join(BASE_DIR, ".ai_provider_install.json")

PROVIDERS = ("auto", "hosted", "openai", "compatible", "none")
LABELS = {
    "auto": "Automatic",
    "hosted": "Built-in AI",
    "openai": "My OpenAI key",
    "compatible": "Local model or other provider",
    "none": "Off (local predictor)",
}
# Proxy refusals that won't change by trying another model.
FINAL_CODES = {"ai_budget", "daily_limit", "rate_limited", "service_busy", "invalid_token",
               "register_limit", "not_configured", "bad_request", "too_large"}
# What the proxy accepts in names and the card-evidence text (prompt.js
# NAME_RE / EXPLAIN_RE): letters and digits of any script plus these.
# A card or deck name as the proxy accepts it (prompt.js NAME_RE): 1-6 words
# of letters/digits and ' ’ . - , each word starting with a letter or digit.
NAME_WORD = re.compile(r"^[^\W_][\w'\u2019.\-]*$")
TIMEOUT = 45.0


class Plan:
    def __init__(self, provider, client=None, models=(), reason=None, json_mode=True):
        self.provider = provider
        self.client = client
        self.models = list(models)
        self.reason = reason          # manual_reason when there is no client
        self.json_mode = json_mode

    def __repr__(self):
        return f"Plan({self.provider}, models={self.models}, reason={self.reason})"


def hosted_available():
    return edition.EDITION == "ai" and bool(edition.HOSTED_AI_URL)


# ── secrets on disk (DPAPI on Windows, like the OpenAI key) ────────────────

def _load_secret(path, plain_path=None):
    if plain_path:
        plain = app_settings._read_text_file(plain_path)
        if plain:
            try:
                _save_secret(path, plain)
                app_settings._remove(plain_path)
            except Exception:
                pass
            return plain
    encoded = app_settings._read_text_file(path)
    if not encoded:
        return None
    if sys.platform != "win32":
        return encoded
    try:
        return app_settings._dpapi(base64.b64decode(encoded), False).decode("utf-8").strip() or None
    except Exception:
        return None


def _save_secret(path, value):
    value = (value or "").strip()
    if not value:
        app_settings._remove(path)
        return
    if sys.platform != "win32":
        app_settings._write_text_file(path, value)
        return
    app_settings._write_text_file(path, base64.b64encode(app_settings._dpapi(value.encode("utf-8"), True))
                                  .decode("ascii"))


def load_compat_key():
    return _load_secret(COMPAT_KEY_FILE, COMPAT_KEY_PLAIN)


def save_compat_key(key):
    _save_secret(COMPAT_KEY_FILE, key)
    app_settings._remove(COMPAT_KEY_PLAIN)


def forget_install_token():
    app_settings._remove(INSTALL_TOKEN_FILE)


# ── settings ──────────────────────────────────────────────────────────────

def apply_installer_choice():
    """The installer's AI page writes .ai_provider_install.json; fold it into
    the app settings once and delete it."""
    if not os.path.exists(INSTALLER_CHOICE_FILE):
        return
    try:
        with open(INSTALLER_CHOICE_FILE, "r", encoding="utf-8") as handle:
            choice = json.load(handle)
    except (OSError, ValueError):
        choice = None
    if isinstance(choice, dict) and choice.get("ai_provider") in PROVIDERS:
        settings = app_settings.load_app_settings()
        settings["ai_provider"] = choice["ai_provider"]
        settings["local_only_mode"] = choice["ai_provider"] == "none"
        for key in ("ai_base_url", "ai_model"):
            if isinstance(choice.get(key), str) and choice[key].strip():
                settings[key] = choice[key].strip()
        app_settings.save_app_settings(settings)
    app_settings._remove(INSTALLER_CHOICE_FILE)


def configured_provider(settings=None):
    """The provider that will actually be used (never "auto")."""
    if settings is None:
        apply_installer_choice()
        settings = app_settings.load_app_settings()
    if settings.get("local_only_mode"):
        return "none"
    choice = settings.get("ai_provider") or "auto"
    if choice not in PROVIDERS:
        choice = "auto"
    if choice == "hosted" and not hosted_available():
        choice = "auto"
    if choice == "auto":
        if app_settings.load_api_key():
            return "openai"
        return "hosted" if hosted_available() else "none"
    return choice


def ai_ready(settings=None):
    """True when a battle would go to an AI (for the manual-mode notices)."""
    provider = configured_provider(settings)
    if provider == "openai":
        return bool(app_settings.load_api_key())
    if provider == "compatible":
        s = settings or app_settings.load_app_settings()
        return bool(s.get("ai_base_url") and s.get("ai_model"))
    return provider == "hosted"


# ── hosted proxy ──────────────────────────────────────────────────────────

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """The proxy never redirects: a redirect is refused (an HTTPError), so the
    install token is never re-sent to another host or over plain http."""

    def redirect_request(self, *_args, **_kwargs):
        return None


def _open(request, timeout):
    # Default context: TLS 1.2+, certificate and host name verified.
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(
        context=ssl.create_default_context()))
    return opener.open(request, timeout=timeout)


def is_local_url(url):
    """http:// is only for a model on this PC or the home network."""
    import ipaddress
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _post_json(url, payload, timeout=20.0):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "content-type": "application/json", "user-agent": _user_agent()})
    with _open(request, timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _user_agent():
    try:
        from version import APP_VERSION
    except Exception:
        APP_VERSION = "?"
    return f"PTCGLMonitor/{APP_VERSION}"


def install_token(register=True):
    """This install's proxy token; registers one on first use."""
    token = _load_secret(INSTALL_TOKEN_FILE)
    if token or not register:
        return token
    base = edition.HOSTED_AI_URL.rstrip("/")
    if not base.lower().startswith("https://"):
        raise RuntimeError("hosted AI URL must be https")
    reply = _post_json(f"{base}/register", {})
    token = str(reply.get("token") or "")
    if not re.fullmatch(r"v1\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}", token):
        raise RuntimeError("the AI service returned no install token")
    _save_secret(INSTALL_TOKEN_FILE, token)
    return token


def is_name(text, limit=40):
    words = str(text).split(" ")
    return (0 < len(text) <= limit and len(words) <= 6 and "_" not in text
            and all(NAME_WORD.match(w) for w in words))


def hosted_fields(fields, evidence=None):
    """The /v1/parse body as the proxy will accept it: an anonymized log,
    deck names and evidence as data. Names it would refuse are left out, so
    one strange name never costs the game its AI answer."""
    if not fields.get("anonymized"):
        raise ValueError("the built-in AI only takes anonymized logs")
    evidence = evidence or {}
    ranked = [[d, max(0, min(100, int(p)))] for d, p in evidence.get("ranked") or [] if is_name(d)][:3]
    revealed = [[c, max(0, min(60, int(n)))] for c, n in evidence.get("revealed") or [] if is_name(c)][:25]
    return {"battlelog": fields["battlelog"], "anonymized": True,
            "decks": [d for d in fields["decks"] if is_name(d)][:60],
            "evidence": {"ranked": ranked, "revealed": revealed} if ranked or revealed else None}


class HostedError(Exception):
    def __init__(self, status, code, message):
        super().__init__(f"Error code: {status} - {code}: {message}")
        self.status_code, self.code = status, code


class HostedClient:
    """POST /v1/parse: the battle log and its fields go up, only the parsed
    deck fields come back (the proxy builds the prompt)."""

    def __init__(self, base_url, token):
        self.url = base_url.rstrip("/") + "/parse"
        self.token = token

    def parse(self, model, fields, evidence=None):
        """-> (payload dict, completion-like object with .usage)"""
        body = json.dumps(dict(hosted_fields(fields, evidence), model=model)).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, method="POST", headers={
            "authorization": f"Bearer {self.token}", "content-type": "application/json",
            "user-agent": _user_agent()})
        try:
            with _open(request, TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                err = json.loads(exc.read().decode("utf-8")).get("error") or {}
            except Exception:
                err = {}
            raise HostedError(exc.code, err.get("code") or "http_error", err.get("message") or exc.reason) from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise HostedError(0, "unreachable", str(exc)) from None
        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            raise HostedError(200, "bad_response", "no result")
        usage = data.get("usage") or {}
        completion = types.SimpleNamespace(model=data.get("model"), usage=types.SimpleNamespace(
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            prompt_tokens_details=types.SimpleNamespace(
                cached_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0))))
        return result, completion


def _openai_client(**kwargs):
    from openai import OpenAI
    return OpenAI(timeout=TIMEOUT, **kwargs)


def resolve(settings=None):
    """The Plan for the next battle."""
    if settings is None:
        apply_installer_choice()
        settings = app_settings.load_app_settings()
    provider = configured_provider(settings)
    if provider == "none":
        return Plan("none", reason="local_only" if settings.get("local_only_mode") or
                    settings.get("ai_provider") == "none" else "no_key")
    if provider == "openai":
        key = app_settings.load_api_key()
        if not key:
            return Plan("openai", reason="no_key")
        # The user's own key: no app-imposed budget, the daily light-model
        # switch still keeps it cheap.
        return Plan("openai", _openai_client(api_key=key, max_retries=1), ai_usage.models_for_now())
    if provider == "compatible":
        base, model = (settings.get("ai_base_url") or "").strip(), (settings.get("ai_model") or "").strip()
        if not base or not model:
            return Plan("compatible", reason="no_key")
        if not base.lower().startswith("https://") and not is_local_url(base):
            # The key (and the battle logs) would cross the internet unencrypted.
            print(f"[AI] Refusing {base}: use https:// for a server outside this PC / home network.")
            return Plan("compatible", reason="ai_failed")
        return Plan("compatible", _openai_client(api_key=load_compat_key() or "not-needed", base_url=base,
                                                 max_retries=0), [model])
    try:
        token = install_token()
    except Exception as exc:
        print(f"[AI] Built-in AI unavailable: {exc}")
        return Plan("hosted", reason="ai_failed")
    # The server enforces the limits and the light-model switch.
    return Plan("hosted", HostedClient(edition.HOSTED_AI_URL, token), ai_usage.MODEL_ORDER)


def error_code(exc):
    """The proxy's error code for an openai SDK exception (or None)."""
    code = getattr(exc, "code", None)
    if code:
        return str(code)
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        return err.get("code")
    return None


def handle_failure(plan, exc):
    """After a failed call: is it final (skip other models), and what manual
    reason does the overlay show?"""
    code = error_code(exc)
    if plan.provider == "hosted" and code == "invalid_token":
        forget_install_token()  # revoked or rotated secret: register again next battle
    if code == "ai_budget":
        return True, "ai_budget"
    return code in FINAL_CODES, "ai_failed"


def hosted_status():
    """{budget_left, reset} from the proxy, or None."""
    if not hosted_available():
        return None
    token = install_token(register=False)
    if not token:
        return None
    request = urllib.request.Request(f"{edition.HOSTED_AI_URL.rstrip('/')}/status", headers={
        "authorization": f"Bearer {token}", "user-agent": _user_agent()})
    try:
        with _open(request, 10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
