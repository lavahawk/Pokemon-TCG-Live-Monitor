"""Tests for updater.py (run: python test_updater.py). No network: GitHub and
downloads are faked; files go to a temp dir."""
import atexit
import hashlib
import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import updater as U

TMP = tempfile.mkdtemp(prefix="updater_test_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
U.tempfile.tempdir = TMP  # downloads land here

PAYLOAD = b"MZ fake installer " * 1000
SHA = hashlib.sha256(PAYLOAD).hexdigest()


def release_json(tag="v9.1.0", with_sum=True):
    assets = [{"name": "PokemonTCGLiveMonitor-9.1.0-Setup.exe", "size": len(PAYLOAD),
               "browser_download_url": "https://x/setup.exe"}]
    if with_sum:
        assets.append({"name": "PokemonTCGLiveMonitor-9.1.0-Setup.exe.sha256",
                       "browser_download_url": "https://x/setup.exe.sha256"})
    return {"tag_name": tag, "html_url": "https://github.com/r/releases/tag/" + tag, "body": "notes",
            "draft": False, "prerelease": False, "assets": assets}


class FakeResp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_for(payload, checksum_text):
    def opener(req, timeout=None):
        url = req.full_url
        return FakeResp(checksum_text.encode() if url.endswith(".sha256") else payload)
    return opener


def test_version_compare():
    assert U.parse_version("v2.10.1") == (2, 10, 1)
    assert U.is_newer("v2.10.0", "2.9.9") and not U.is_newer("2.7.0", "2.7.0")
    assert not U.is_newer("garbage", "2.7.0")


def test_latest_release_parsing():
    rel = U.latest_release(fetch=lambda url: release_json())
    assert rel["version"] == "9.1.0" and rel["installer"]["name"].endswith("Setup.exe")
    assert rel["sha256_url"].endswith(".sha256")
    assert U.latest_release(fetch=lambda url: dict(release_json(), prerelease=True)) is None

    def offline(url):
        raise OSError("offline")
    assert U.latest_release(fetch=offline) is None


def test_update_available_and_skip():
    fetch = lambda url: release_json()  # noqa: E731
    assert U.update_available({}, fetch=fetch, current="2.7.0")["version"] == "9.1.0"
    assert U.update_available({"skip_update_version": "9.1.0"}, fetch=fetch, current="2.7.0") is None
    assert U.update_available({}, fetch=fetch, current="9.1.0") is None


def test_self_install_only_for_installed_copies():
    installed = os.path.join(TMP, "installed")
    os.makedirs(os.path.join(installed, "runtime"))
    open(os.path.join(installed, "runtime", "pythonw.exe"), "w").close()
    assert U.can_self_install(installed)
    os.makedirs(os.path.join(installed, ".git"))
    assert not U.can_self_install(installed)  # a git checkout is never overwritten


def test_download_verifies_checksum():
    rel = U.latest_release(fetch=lambda url: release_json())
    seen = []
    path = U.download(rel, progress=lambda d, t: seen.append((d, t)),
                      opener=opener_for(PAYLOAD, f"{SHA}  PokemonTCGLiveMonitor-9.1.0-Setup.exe"))
    assert open(path, "rb").read() == PAYLOAD and seen[-1] == (len(PAYLOAD), len(PAYLOAD))
    try:
        U.download(rel, opener=opener_for(PAYLOAD, "0" * 64))
        raise AssertionError("a checksum mismatch must fail")
    except RuntimeError as exc:
        assert "checksum" in str(exc)


def test_installer_matches_edition():
    assets = [{"name": "PokemonTCGLiveMonitor-2.8.0-Free-Setup.exe"}, {"name": "PokemonTCGLiveMonitor-2.8.0-Setup.exe"},
              {"name": "PokemonTCGLiveMonitor-2.8.0-Setup.exe.sha256"}]
    assert U._pick_installer(assets, "ai")["name"] == "PokemonTCGLiveMonitor-2.8.0-Setup.exe"
    assert U._pick_installer(assets, "free")["name"] == "PokemonTCGLiveMonitor-2.8.0-Free-Setup.exe"
    # Older releases have one Setup.exe: the free build takes it, the AI build never takes a free one.
    assert U._pick_installer(assets[1:], "free")["name"] == "PokemonTCGLiveMonitor-2.8.0-Setup.exe"
    assert U._pick_installer(assets[:1], "ai") is None


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
