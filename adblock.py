"""
Lightweight ad / tracker blocking for the app's built-in browser tabs
(Limitless, TrainerHill, Replay, PokeData, In Person).

A QWebEngineUrlRequestInterceptor on every web profile cancels requests to
hosts in adblock_hosts.txt (a domain blocks its subdomains). Requests to the
page's own site are never blocked, so a site can't break itself. No cosmetic
filtering: blocked ad slots may leave empty space.

Setting: "browser_adblock" in .app_settings.json (default on), toggled from
Settings → Overlay; takes effect on the next request.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOSTS_FILE = os.path.join(BASE_DIR, "adblock_hosts.txt")

_state = {"hosts": None, "enabled": None, "blocked": 0, "interceptor": None, "profiles": set()}


def load_hosts(path=HOSTS_FILE):
    hosts = set()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.split("#", 1)[0].strip().lower().lstrip(".")
                if line:
                    hosts.add(line)
    except OSError:
        pass
    return hosts


def _site(host):
    """Registrable-ish part of a host (last two labels): enough to tell a
    page's own resources from third parties."""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def is_blocked(host, first_party_host="", hosts=None):
    host = (host or "").lower().rstrip(".")
    if not host:
        return False
    if first_party_host and _site(host) == _site(first_party_host.lower()):
        return False
    hosts = _state["hosts"] if hosts is None else hosts
    if hosts is None:
        hosts = _state["hosts"] = load_hosts()
    labels = host.split(".")
    return any(".".join(labels[i:]) in hosts for i in range(len(labels) - 1))


def set_enabled(enabled):
    _state["enabled"] = bool(enabled)


def enabled():
    if _state["enabled"] is None:
        try:
            from app_settings import load_app_settings
            _state["enabled"] = bool(load_app_settings().get("browser_adblock", True))
        except Exception:
            _state["enabled"] = True
    return _state["enabled"]


def blocked_count():
    return _state["blocked"]


def _interceptor():
    if _state["interceptor"] is None:
        from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor

        class AdblockInterceptor(QWebEngineUrlRequestInterceptor):
            def interceptRequest(self, info):
                if not enabled():
                    return
                try:
                    host = info.requestUrl().host()
                    first = info.firstPartyUrl().host()
                    if is_blocked(host, first):
                        info.block(True)
                        _state["blocked"] += 1
                except Exception:
                    pass

        _state["interceptor"] = AdblockInterceptor()
    return _state["interceptor"]


def install(profile=None):
    """Attach the blocker to a QWebEngineProfile (default profile if None).
    Safe to call more than once per profile; never raises."""
    try:
        if profile is None:
            from PySide6.QtWebEngineCore import QWebEngineProfile
            profile = QWebEngineProfile.defaultProfile()
        key = id(profile)
        if key in _state["profiles"]:
            return True
        profile.setUrlRequestInterceptor(_interceptor())
        _state["profiles"].add(key)
        return True
    except Exception as exc:
        print(f"[Adblock] not installed: {exc}")
        return False
