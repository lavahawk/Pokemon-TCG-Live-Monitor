"""
One-shot setup script run by the Inno Setup installer.

Handles everything needed to make the app functional after the files are
copied: creates the virtual environment, installs Python dependencies,
downloads Tesseract OCR (with fallbacks), and configures auto-start.

This is invoked directly by the installer (not a separate .bat the user runs).
"""

import os
import subprocess
import sys
import urllib.request
import zipfile
import shutil
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(BASE_DIR, ".venv")
TESS_DIR = os.path.join(BASE_DIR, "tesseract")
REQUIREMENTS = os.path.join(BASE_DIR, "requirements.txt")

# Tesseract download mirrors (tried in order, with fallbacks).
TESSERACT_URLS = [
    "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe",
    "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe",
]


def log(msg):
    print(f"[setup] {msg}", flush=True)


def run(cmd, **kwargs):
    log("Running: " + " ".join(cmd))
    return subprocess.run(cmd, **kwargs)


def create_venv():
    """Create the virtual environment if it doesn't exist."""
    if os.path.exists(os.path.join(VENV_DIR, "Scripts", "python.exe")):
        log("Virtual environment already exists.")
        return True
    log("Creating virtual environment...")
    result = run([sys.executable, "-m", "venv", VENV_DIR])
    return result.returncode == 0


def venv_python():
    return os.path.join(VENV_DIR, "Scripts", "python.exe")


def install_dependencies():
    """Install Python dependencies into the venv."""
    python = venv_python()
    if not os.path.exists(python):
        log("ERROR: venv python not found.")
        return False

    log("Upgrading pip...")
    run([python, "-m", "pip", "install", "--upgrade", "pip", "--quiet", "--disable-pip-version-check"])

    log("Installing dependencies from requirements.txt...")
    result = run([python, "-m", "pip", "install", "-r", REQUIREMENTS, "--quiet", "--disable-pip-version-check"])
    if result.returncode == 0:
        log("Dependencies installed successfully.")
        return True

    # Fallback: install core packages individually.
    log("requirements.txt install failed. Trying individual core packages...")
    core = [
        "psutil==5.9.8", "pyperclip==1.8.2", "pygame==2.5.2", "pyfiglet==1.0.2",
        "colorama==0.4.6", "pandas==2.2.0", "pyarrow==22.0.0", "openpyxl==3.1.2",
        "xlwings==0.30.13", "openai==1.12.0", "pydantic==2.6.1",
        "numpy==1.26.4", "opencv-python==4.9.0.80", "pytesseract==0.3.10",
        "mss==9.0.1", "Pillow==10.2.0", "pywin32==306",
        "PySide6==6.10.1", "matplotlib==3.8.2",
        "beautifulsoup4>=4.12.0", "lxml>=5.0.0", "requests>=2.31.0",
    ]
    ok = True
    for pkg in core:
        r = run([python, "-m", "pip", "install", pkg, "--quiet", "--disable-pip-version-check"])
        if r.returncode != 0:
            log(f"  WARNING: could not install {pkg}")
            ok = False
    return ok


def _find_7z():
    """Locate 7-Zip for extracting the Tesseract installer without elevation."""
    candidates = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        os.path.expandvars(r"%ProgramFiles%\7-Zip\7z.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return shutil.which("7z")


def download_tesseract():
    """Download and extract portable Tesseract OCR with fallbacks.

    Tries, in order:
      1. Extract the installer with 7-Zip (no admin needed).
      2. Run the installer silently to the local folder (may need admin).
      3. Fall back to a clear message pointing to manual install.
    """
    if os.path.exists(os.path.join(TESS_DIR, "tesseract.exe")):
        log("Tesseract already present locally.")
        return True

    os.makedirs(TESS_DIR, exist_ok=True)
    installer = os.path.join(tempfile.gettempdir(), "tesseract-setup.exe")

    for url in TESSERACT_URLS:
        log(f"Downloading Tesseract from {url} ...")
        try:
            urllib.request.urlretrieve(url, installer)
            if not (os.path.exists(installer) and os.path.getsize(installer) > 1000000):
                log("  Download invalid. Trying next mirror...")
                continue

            # Method 1: extract with 7-Zip (no admin).
            seven_zip = _find_7z()
            if seven_zip:
                log("Extracting with 7-Zip to local folder (no admin)...")
                subprocess.run([seven_zip, "x", installer, f"-o{TESS_DIR}", "-y"], timeout=180)
                if os.path.exists(os.path.join(TESS_DIR, "tesseract.exe")):
                    log("Tesseract ready locally (7-Zip).")
                    try:
                        os.remove(installer)
                    except Exception:
                        pass
                    return True

            # Method 2: run the installer silently to the local folder.
            log("Running installer silently to local folder...")
            subprocess.run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={TESS_DIR}"], timeout=180)
            if os.path.exists(os.path.join(TESS_DIR, "tesseract.exe")):
                log("Tesseract ready locally.")
                try:
                    os.remove(installer)
                except Exception:
                    pass
                return True

            log("  Extraction/install did not produce tesseract.exe. Trying next mirror...")
        except Exception as exc:
            log(f"  Download error: {exc}. Trying next mirror...")

    log("WARNING: Could not download Tesseract automatically.")
    log("Rank detection will be limited until Tesseract is installed.")
    log("Install it to: " + TESS_DIR + "  (or C:\\Program Files\\Tesseract-OCR)")
    return False


def configure_startup():
    """Configure auto-start via the registry Run key (no admin needed)."""
    pythonw = os.path.join(VENV_DIR, "Scripts", "pythonw.exe")
    script = os.path.join(BASE_DIR, "TCGLiveMonitor.py")
    if not os.path.exists(pythonw) or not os.path.exists(script):
        log("WARNING: Could not configure auto-start (venv or script missing).")
        return False

    command = f'"{pythonw}" "{script}" --headless'
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            winreg.SetValueEx(key, "PokemonTCGLiveMonitor", 0, winreg.REG_SZ, command)
        log("Auto-start configured via registry.")
        return True
    except Exception as exc:
        log(f"WARNING: Could not configure auto-start: {exc}")
        return False


def main():
    log("=== Pokemon TCG Live Monitor Setup ===")
    log(f"Install dir: {BASE_DIR}")

    ok = True
    ok = create_venv() and ok
    ok = install_dependencies() and ok
    download_tesseract()  # non-fatal
    configure_startup()   # non-fatal

    log("=== Setup complete ===")
    if ok:
        log("The app is ready to use.")
    else:
        log("Some components failed. See messages above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())