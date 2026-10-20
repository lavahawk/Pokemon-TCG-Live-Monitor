"""
Update check: is there a newer release on GitHub, and installing it.

  latest_release()   the newest published release: version, notes, page and
                     the Setup.exe (+ .sha256) assets
  update_available() latest_release() when it's newer than this copy and not
                     skipped by the user, else None
  download()         the installer to %TEMP%, SHA-256 checked against the
                     release's .sha256 file
  launch_installer() runs it silently over this install (/VERYSILENT); the
                     installer stops the running app, keeps battles and
                     settings, and starts the monitor again (/RELAUNCH=1)

Only an installed copy (runtime\\pythonw.exe next to the app, no .git folder)
installs itself; a dev checkout is pointed at the release page instead.
No Qt here: the overlay runs the network parts on a worker thread.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

from version import APP_VERSION

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = "lavahawk/Pokemon-TCG-Live-Monitor"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
INSTALLER_NAME = re.compile(r"Setup\.exe$", re.IGNORECASE)
FREE_NAME = re.compile(r"-Free-Setup\.exe$", re.IGNORECASE)


def parse_version(text):
    """"v2.10.1" -> (2, 10, 1); junk -> ()."""
    numbers = re.findall(r"\d+", str(text or ""))
    return tuple(int(n) for n in numbers[:3])


def is_newer(remote, local=APP_VERSION):
    r, l = parse_version(remote), parse_version(local)
    return bool(r) and r > l


def _get_json(url, timeout=15):
    from urllib.request import Request, urlopen
    req = Request(url, headers={"User-Agent": "PTCGL-Monitor-Updater", "Accept": "application/vnd.github+json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pick_installer(assets, edition=None):
    """The Setup.exe of this edition: "...-Free-Setup.exe" for the free
    build, the other one for the AI build (never the free one: it would
    drop the built-in AI)."""
    if edition is None:
        try:
            import edition as _edition
            edition = _edition.EDITION
        except Exception:
            edition = "ai"
    setups = [a for a in assets if INSTALLER_NAME.search(a.get("name") or "")]
    free = [a for a in setups if FREE_NAME.search(a.get("name") or "")]
    full = [a for a in setups if a not in free]
    if edition == "free":
        return (free or full or [None])[0]
    return (full or [None])[0]


def latest_release(fetch=None):
    """{"version", "tag", "page", "notes", "installer": {"name", "url", "size"}, "sha256_url"}
    or None (no release / offline). fetch(url) -> parsed JSON (tests)."""
    try:
        data = (fetch or _get_json)(LATEST_API)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    assets = data.get("assets") or []
    installer = _pick_installer(assets)
    checksum = None
    if installer:
        checksum = next((a for a in assets if (a.get("name") or "") == installer["name"] + ".sha256"), None)
    return {
        "version": ".".join(str(n) for n in parse_version(data.get("tag_name"))) or data.get("tag_name"),
        "tag": data.get("tag_name"),
        "page": data.get("html_url") or RELEASES_PAGE,
        "notes": data.get("body") or "",
        "installer": ({"name": installer["name"], "url": installer.get("browser_download_url"),
                       "size": int(installer.get("size") or 0)} if installer else None),
        "sha256_url": checksum.get("browser_download_url") if checksum else None,
    }


def update_available(settings=None, fetch=None, current=APP_VERSION):
    """The newer release, unless it's the version the user chose to skip."""
    release = latest_release(fetch)
    if not release or not is_newer(release["version"], current):
        return None
    skipped = (settings or {}).get("skip_update_version")
    if skipped and parse_version(skipped) == parse_version(release["version"]):
        return None
    return release


def can_self_install(base_dir=BASE_DIR):
    """An installed copy (bundled runtime) can run the new installer over
    itself; a git checkout must not be overwritten."""
    return (os.path.exists(os.path.join(base_dir, "runtime", "pythonw.exe"))
            and not os.path.isdir(os.path.join(base_dir, ".git")))


def _expected_sha256(url, opener=None):
    from urllib.request import Request, urlopen
    req = Request(url, headers={"User-Agent": "PTCGL-Monitor-Updater"})
    with (opener or urlopen)(req, timeout=15) as resp:
        text = resp.read().decode("utf-8", "replace")
    match = re.search(r"\b[0-9a-fA-F]{64}\b", text)
    return match.group(0).lower() if match else None


def download(release, progress=None, cancelled=None, opener=None):
    """Download the installer to %TEMP%\\PTCGLMonitorUpdate\\; progress(done, total).
    Returns the file path. Raises on failure, a checksum mismatch or cancel."""
    from urllib.request import Request, urlopen
    installer = (release or {}).get("installer")
    if not installer or not installer.get("url"):
        raise RuntimeError("This release has no installer to download.")
    folder = os.path.join(tempfile.gettempdir(), "PTCGLMonitorUpdate")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, os.path.basename(installer["name"]))
    if not release.get("sha256_url"):
        raise RuntimeError("This release has no checksum file, so the download can't be verified - nothing was installed.")
    expected = _expected_sha256(release["sha256_url"], opener)
    if not expected:
        raise RuntimeError("The release checksum file has no valid SHA-256 digest - nothing was installed.")
    req = Request(installer["url"], headers={"User-Agent": "PTCGL-Monitor-Updater"})
    digest = hashlib.sha256()
    with (opener or urlopen)(req, timeout=60) as resp, open(path + ".part", "wb") as out:
        total = int(resp.headers.get("Content-Length") or installer.get("size") or 0)
        done = 0
        while True:
            if cancelled is not None and cancelled():
                raise RuntimeError("Download cancelled.")
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress is not None:
                progress(done, total)
    if digest.hexdigest().lower() != expected:
        os.remove(path + ".part")
        raise RuntimeError("The download didn't match the release checksum - nothing was installed.")
    os.replace(path + ".part", path)
    return path


def launch_installer(path, base_dir=BASE_DIR):
    """Start the installer silently, detached from this process. It stops
    the running app itself, installs into the same folder (UsePreviousAppDir)
    and starts the monitor again. The installer only replaces program files;
    battles, settings, keys and logs are left alone - and are copied to
    Backups\pre-update-<time>\ first anyway."""
    try:
        from datatransfer import backup_now
        backup_now("pre-update", base_dir)
    except Exception:
        pass  # a failed safety copy must not block the update
    # Log outside the app folder: the installer stops processes whose command
    # line mentions the app folder.
    log = os.path.join(tempfile.gettempdir(), "PTCGLMonitorUpdate", "install.log")
    args = [path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1", f"/LOG={log}"]
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(args, cwd=os.path.dirname(path), creationflags=flags, close_fds=True)
