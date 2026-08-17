# Pokemon TCG Live Monitor v2.3 - Release Notes

**Release Date:** August 16, 2026

## Overview

v2.3 focuses on **performance, reliability, and a smoother experience for everyone** — including users who don't have an OpenAI API key. Deck icon menus now load instantly, new installs no longer hit a numpy/OpenCV compatibility crash, and the local-only fallback is clearer and easier to use.

---

## What's New in v2.3

### Performance
- **Faster deck icon menus** — Sprite icons are now cached in memory, so opening the deck icon picker and switching between deck dashboards is dramatically faster (no repeated disk reads / re-scaling).
- **Cached icon choices** — The list of available Pokemon icons is computed once and reused, instead of re-scanning the cache directory every time the picker opens.

### Reliability
- **Fixed numpy/OpenCV crash on new installs** — `opencv-python 4.9.0.80` is compiled against numpy 1.x, but numpy 2.x was being installed, causing a `numpy.dtype size changed` binary incompatibility error during rank detection. numpy is now pinned to `1.26.4` in `requirements.txt` and the installer.
- **Complete dependency set** — The installer now also installs the meta-analysis packages (`beautifulsoup4`, `lxml`, `requests`) that were missing from the batch installer.

### Local-Only Mode (No API Key)
- **Clearer messaging** — When no API key is present, the app now clearly explains it is running in local-only mode and guides you through manual deck entry.
- **Works out of the box** — You can use the full monitor, OCR rank/deck detection, overlay, and stats database without an API key. AI deck analysis is simply skipped.

### Installer & Build
- **Updated to v2.3** across all scripts, scheduled tasks, and release packaging.
- **New files included in release** — `app_settings.py`, `deck_analytics.py`, and `startup_utils.py` are now bundled so the release ZIP is complete and functional.
- **Stale references cleaned up** — Removed outdated v2.1/v2.0 references from launchers and docs.

---

## Upgrade from v2.2
1. Stop the current monitor (Stats Dashboard → Advanced → Close Application)
2. Replace all `.py` files and `Installers\` batch files with v2.3 versions
3. Re-run `Installers\INSTALL_COMPLETE_v2.3.bat` as Administrator to update the scheduled task

---

## System Requirements
- Windows 10 / 11
- Python 3.10+
- Tesseract OCR 5.x (auto-installed)
- ~500 MB disk space