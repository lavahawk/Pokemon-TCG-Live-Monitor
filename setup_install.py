"""
One-shot setup, run by bootstrap_setup.ps1 (which picks a compatible Python).

Steps:
  1. Create/repair the .venv (recreated if it was built with an incompatible
     Python, e.g. 3.13, where the pinned wheels don't exist).
  2. pip install -r requirements.txt, then verify the key imports.
  3. Download portable Tesseract OCR if it isn't available (signature checked).
  4. Register auto-start (HKCU Run key -> pythonw TCGLiveMonitor.py --headless),
     remove legacy scheduled tasks.
  5. Optionally launch the monitor.

Usage: python setup_install.py [--autostart | --no-autostart] [--launch]
(no auto-start flag = keep the current auto-start setting)
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(BASE_DIR, ".venv")
TESS_DIR = os.path.join(BASE_DIR, "tesseract")
REQUIREMENTS = os.path.join(BASE_DIR, "requirements.txt")
LOG_FILE = os.path.join(BASE_DIR, "Logs", "setup.log")

# UB Mannheim build (the one linked from the official Tesseract docs).
TESSERACT_URL = (
    "https://github.com/UB-Mannheim/tesseract/releases/download/"
    "v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
)
VERIFY_IMPORTS = "import PySide6, cv2, numpy, mss, pytesseract, psutil, pyperclip, win32gui, matplotlib, openpyxl, requests"


def log(msg):
    line = f"[setup] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def run(cmd, **kwargs):
    log("Running: " + " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, **kwargs)


def venv_python(windowed=False):
    return os.path.join(VENV_DIR, "Scripts", "pythonw.exe" if windowed else "python.exe")


def _python_minor(exe):
    try:
        out = subprocess.run([exe, "-c", "import sys; print(sys.version_info[1])"],
                             capture_output=True, text=True, timeout=30)
        return int(out.stdout.strip())
    except Exception:
        return None


def create_venv():
    if sys.version_info[:2] < (3, 10) or sys.version_info[:2] > (3, 12):
        log(f"WARNING: running under Python {sys.version.split()[0]}; 3.10-3.12 is required for the pinned packages.")
    existing = venv_python()
    if os.path.exists(existing):
        minor = _python_minor(existing)
        if minor is not None and 10 <= minor <= 12:
            log("Virtual environment already exists.")
            return True
        log(f"Existing .venv uses Python 3.{minor}; recreating it.")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
    log("Creating virtual environment...")
    return run([sys.executable, "-m", "venv", VENV_DIR]).returncode == 0


def install_dependencies():
    python = venv_python()
    if not os.path.exists(python):
        log("ERROR: venv python not found.")
        return False
    run([python, "-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check", "-q"])
    log("Installing dependencies (this can take several minutes)...")
    if run([python, "-m", "pip", "install", "-r", REQUIREMENTS, "--disable-pip-version-check"]).returncode != 0:
        log("ERROR: pip could not install the requirements. See the output above.")
        return False
    check = run([python, "-c", VERIFY_IMPORTS], capture_output=True, text=True)
    if check.returncode != 0:
        log("ERROR: dependencies installed but failed to import:\n" + (check.stderr or "")[-2000:])
        return False
    log("Dependencies installed and verified.")
    return True


def _tesseract_available():
    candidates = [
        os.path.join(TESS_DIR, "tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    return any(os.path.exists(c) for c in candidates) or shutil.which("tesseract")


def _signature_ok(path):
    """Authenticode check via PowerShell (Windows only)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"(Get-AuthenticodeSignature '{path}').Status"],
            capture_output=True, text=True, timeout=60,
        )
        return out.stdout.strip() == "Valid"
    except Exception:
        return False


def _find_7z():
    for c in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if os.path.exists(c):
            return c
    return shutil.which("7z")


def download_tesseract():
    if _tesseract_available():
        log("Tesseract OCR found.")
        return True
    workdir = tempfile.mkdtemp(prefix="tcgmon-tess-")
    installer = os.path.join(workdir, "tesseract-setup.exe")
    try:
        log("Downloading Tesseract OCR...")
        urllib.request.urlretrieve(TESSERACT_URL, installer)
        if not _signature_ok(installer):
            log("WARNING: Tesseract installer signature is not valid - not running it.")
            return False
        os.makedirs(TESS_DIR, exist_ok=True)
        seven_zip = _find_7z()
        if seven_zip:
            run([seven_zip, "x", installer, f"-o{TESS_DIR}", "-y"], timeout=300, capture_output=True)
        if not os.path.exists(os.path.join(TESS_DIR, "tesseract.exe")):
            run([installer, "/S", f"/D={TESS_DIR}"], timeout=300)
        ok = os.path.exists(os.path.join(TESS_DIR, "tesseract.exe"))
        log("Tesseract ready." if ok else "WARNING: Tesseract install did not produce tesseract.exe.")
        return ok
    except Exception as exc:
        log(f"WARNING: Tesseract download failed: {exc}")
        return False
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def configure_startup(enable):
    sys.path.insert(0, BASE_DIR)
    try:
        import startup_utils
    except Exception as exc:
        log(f"WARNING: startup helpers unavailable: {exc}")
        return False
    if not enable:
        startup_utils.remove_registry()
        log("Auto-start not enabled (you can enable it later from the dashboard).")
        return True
    report = startup_utils.enable_startup(BASE_DIR)
    if report["registry_ok"] or report["task_ok"]:
        log("Auto-start enabled (starts hidden at login and waits for Pokemon TCG Live).")
        if report.get("removed_tasks"):
            log("Removed old scheduled tasks: " + ", ".join(report["removed_tasks"]))
        return True
    log(f"WARNING: could not enable auto-start: {report.get('registry_error') or report.get('task_error')}")
    return False


def launch():
    pythonw = venv_python(windowed=True)
    if not os.path.exists(pythonw):
        return
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([pythonw, os.path.join(BASE_DIR, "TCGLiveMonitor.py"), "--headless"],
                     cwd=BASE_DIR, creationflags=flags, close_fds=True)
    log("Monitor launched in the background.")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--autostart", dest="autostart", action="store_const", const=True, default=None)
    group.add_argument("--no-autostart", dest="autostart", action="store_const", const=False)
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args()

    log("=== Pokemon TCG Live Monitor setup ===")
    log(f"Install dir: {BASE_DIR}")
    log(f"Python: {sys.executable} ({sys.version.split()[0]})")

    if not create_venv() or not install_dependencies():
        log("Setup FAILED. Fix the error above and run setup again.")
        return 1
    download_tesseract()  # non-fatal: OCR rank detection needs it
    if args.autostart is not None:  # None = leave the current auto-start setting alone
        configure_startup(args.autostart)
    if args.launch:
        launch()
    log("=== Setup complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
