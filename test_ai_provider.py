"""Tests for ai_provider.py (run: python test_ai_provider.py). Settings, keys and
tokens live in a temp folder; the hosted proxy is a local mock server that
answers like ai_proxy/src/worker.js (no internet, no real key)."""
import atexit
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TMP = tempfile.mkdtemp(prefix="ai_provider_test_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

# Importing AIParseBattleLog opens the DB: point it at a temp file first.
import BattleDatabase as BDB
BDB.DB_PATH = os.path.join(TMP, "parser.db")
BDB.BattleDatabase.__init__.__defaults__ = (BDB.DB_PATH, False)
import meta_sources


def _no_network(*_a, **_k):
    raise AssertionError("network access in a test")


meta_sources._api_get = _no_network
import AIParseBattleLog as P
import ai_provider as A
import ai_usage
import app_settings as S
import edition as E

ai_usage.USAGE_FILE = os.path.join(TMP, "ledger", ".ai_usage.json")
os.makedirs(os.path.dirname(ai_usage.USAGE_FILE))
P.LIMITLESS_STANDARD_CACHE_FILE = os.path.join(TMP, "ledger", "meta_cache.json")  # absent
S.API_KEY_FILE = os.path.join(TMP, ".openai_key")
S.API_KEY_SECURE_FILE = os.path.join(TMP, ".openai_key.dpapi")
S.APP_SETTINGS_FILE = os.path.join(TMP, ".app_settings.json")
A.INSTALL_TOKEN_FILE = os.path.join(TMP, ".ai_install.dpapi")
A.COMPAT_KEY_FILE = os.path.join(TMP, ".ai_compat_key.dpapi")
A.COMPAT_KEY_PLAIN = os.path.join(TMP, ".ai_compat_key")
A.INSTALLER_CHOICE_FILE = os.path.join(TMP, ".ai_provider_install.json")
TOKEN = "v1." + "A" * 22 + "." + "B" * 43


def reset(edition="ai", url=""):
    for name in os.listdir(TMP):
        if name.startswith("."):
            os.remove(os.path.join(TMP, name))
    E.EDITION, E.HOSTED_AI_URL = edition, url


def settings(**values):
    S.save_app_settings(values)


# ── mock proxy ──────────────────────────────────────────────────────────────
class _Proxy(http.server.BaseHTTPRequestHandler):
    reply = (200, {})
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])) or b"{}")
        _Proxy.seen.append((self.path, self.headers.get("authorization"), body))
        status, payload = _Proxy.reply
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Proxy)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
atexit.register(SERVER.shutdown)
MOCK_URL = f"http://127.0.0.1:{SERVER.server_address[1]}/v1"

COMPLETION = {"id": "x", "object": "chat.completion", "created": 0, "model": "gpt-4.1-nano",
              "choices": [{"index": 0, "finish_reason": "stop", "message": {
                  "role": "assistant", "content": '{"My_deck": "A", "OpponentsDeck": "B", "Win_or_Loss": "Win", '
                                                  '"Confidence": 60}'}}],
              "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


# ── provider choice ─────────────────────────────────────────────────────────
def test_auto_prefers_own_key_then_hosted_then_none():
    reset()
    assert A.configured_provider() == "none"
    assert A.resolve().reason == "no_key"
    reset(url="https://proxy.example/v1")
    assert A.configured_provider() == "hosted"
    S.save_api_key("sk-own")
    assert A.configured_provider() == "openai"
    reset(edition="free", url="https://proxy.example/v1")
    assert not A.hosted_available() and A.configured_provider() == "none"


def test_local_only_and_hosted_without_url():
    reset(url="https://proxy.example/v1")
    settings(local_only_mode=True, ai_provider="hosted")
    plan = A.resolve()
    assert plan.provider == "none" and plan.reason == "local_only" and plan.client is None
    reset()
    settings(ai_provider="hosted")  # free/dev build: hosted unavailable -> auto
    assert A.configured_provider() == "none"


def test_installer_choice_is_applied_once():
    reset()
    with open(A.INSTALLER_CHOICE_FILE, "w", encoding="utf-8") as handle:
        json.dump({"ai_provider": "compatible", "ai_base_url": " http://localhost:11434/v1 ",
                   "ai_model": "llama3.1"}, handle)
    with open(A.COMPAT_KEY_PLAIN, "w", encoding="utf-8") as handle:
        handle.write("ollama-key")
    assert A.configured_provider() == "compatible"
    loaded = S.load_app_settings()
    assert loaded["ai_base_url"] == "http://localhost:11434/v1" and loaded["local_only_mode"] is False
    assert not os.path.exists(A.INSTALLER_CHOICE_FILE)
    assert A.load_compat_key() == "ollama-key" and not os.path.exists(A.COMPAT_KEY_PLAIN)
    assert A.load_compat_key() == "ollama-key"  # from the encrypted file now
    plan = A.resolve()
    assert plan.provider == "compatible" and plan.models == ["llama3.1"]


def test_installer_choice_none_sets_local_only():
    reset(url="https://proxy.example/v1")
    with open(A.INSTALLER_CHOICE_FILE, "w", encoding="utf-8") as handle:
        json.dump({"ai_provider": "none"}, handle)
    assert A.configured_provider() == "none" and S.load_app_settings()["local_only_mode"] is True


def test_compatible_needs_url_and_model():
    reset()
    settings(ai_provider="compatible", ai_base_url="http://localhost:1234/v1")
    assert A.resolve().reason == "no_key" and not A.ai_ready()


# ── hosted token ────────────────────────────────────────────────────────────
def test_install_token_registers_once_and_is_encrypted():
    reset(url="https://proxy.example/v1")
    calls = []
    saved = A._post_json
    A._post_json = lambda url, payload, timeout=20.0: calls.append(url) or {"token": TOKEN}
    try:
        assert A.install_token() == TOKEN and A.install_token() == TOKEN
        assert calls == ["https://proxy.example/v1/register"]
        with open(A.INSTALL_TOKEN_FILE, encoding="utf-8") as handle:
            stored = handle.read()
        assert TOKEN not in stored or sys.platform != "win32"
        plan = A.resolve()
        assert plan.provider == "hosted" and plan.client is not None and plan.reason is None
    finally:
        A._post_json = saved


def test_bad_or_insecure_registration_is_refused():
    reset(url="https://proxy.example/v1")
    saved = A._post_json
    A._post_json = lambda *a, **k: {"token": "sk-not-a-token"}
    try:
        plan = A.resolve()
        assert plan.client is None and plan.reason == "ai_failed"
        assert not os.path.exists(A.INSTALL_TOKEN_FILE)
    finally:
        A._post_json = saved
    reset(url="http://proxy.example/v1")
    try:
        A.install_token()
        assert False, "plain http must be refused"
    except RuntimeError:
        pass


# ── calls through the real openai SDK against the mock proxy ───────────────
def _hosted_plan():
    reset(url=MOCK_URL)
    A._save_secret(A.INSTALL_TOKEN_FILE, TOKEN)
    return A.resolve()


def test_hosted_call_sends_token_and_parses():
    plan = _hosted_plan()
    _Proxy.seen, _Proxy.reply = [], (200, COMPLETION)
    out = P.ai_parse("me's Turn\nopp's Turn", "me", plan=plan, anonymize=False)
    path, auth, body = _Proxy.seen[0]
    assert path == "/v1/chat/completions" and auth == f"Bearer {TOKEN}"
    assert body["model"] == P.AI_MODELS[0] and body["response_format"] == {"type": "json_object"}
    assert out["OpponentsDeck"] in ("B", out["OpponentsDeck"]) and out["Win_or_Loss"] == "Win"


def test_budget_refusal_is_final_and_reported():
    plan = _hosted_plan()
    _Proxy.seen = []
    _Proxy.reply = (429, {"error": {"code": "ai_budget", "message": "Monthly AI allowance used.",
                                    "type": "proxy_error"}})
    try:
        P.ai_parse("x", "me", plan=plan, anonymize=False)
        assert False, "should raise"
    except Exception as exc:
        assert A.handle_failure(plan, exc) == (True, "ai_budget")
    assert len(_Proxy.seen) == 1  # no retries, no other models


def test_revoked_token_is_forgotten():
    plan = _hosted_plan()
    _Proxy.reply = (401, {"error": {"code": "invalid_token", "message": "Unknown install."}})
    try:
        P.ai_parse("x", "me", plan=plan, anonymize=False)
        assert False, "should raise"
    except Exception:
        pass
    assert not os.path.exists(A.INSTALL_TOKEN_FILE)


def test_upstream_error_tries_next_model():
    plan = _hosted_plan()
    _Proxy.seen = []
    _Proxy.reply = (502, {"error": {"code": "upstream_error", "message": "failed"}})
    try:
        P.ai_parse("x", "me", plan=plan, anonymize=False)
    except Exception as exc:
        assert A.handle_failure(plan, exc) == (False, "ai_failed")
    assert [b["model"] for _p, _a, b in _Proxy.seen] == P.AI_MODELS


def test_local_model_without_json_mode_and_fenced_reply():
    reset()
    settings(ai_provider="compatible", ai_base_url=MOCK_URL, ai_model="qwen2.5")
    plan = A.resolve()
    fenced = dict(COMPLETION, choices=[{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": 'Sure!\n```json\n{"My_deck": "A", "OpponentsDeck": "B", '
                                        '"Win_or_Loss": "Loss", "Confidence": 40}\n```'}}])
    replies = [(400, {"error": {"message": "response_format json_object is not supported"}}), (200, fenced)]
    _Proxy.seen = []

    class _Seq(_Proxy):
        def do_POST(self):
            _Proxy.reply = replies.pop(0)
            _Proxy.do_POST(self)
    SERVER.RequestHandlerClass = _Seq
    try:
        out = P.ai_parse("x", "me", plan=plan, anonymize=False)
    finally:
        SERVER.RequestHandlerClass = _Proxy
    assert out["Win_or_Loss"] == "Loss"
    assert "response_format" in _Proxy.seen[0][2] and "response_format" not in _Proxy.seen[1][2]


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
