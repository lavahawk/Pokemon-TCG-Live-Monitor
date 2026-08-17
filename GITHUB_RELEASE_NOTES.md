# GitHub Release Notes for v2.3.0

Copy this into the GitHub release page:

---

## Title:
Pokemon TCG Live Monitor v2.3.0 - Performance & Reliability

## Description:

# Pokemon TCG Live Monitor v2.3.0

**Professional battle tracking system with AI analysis, OCR rank detection, and modern overlay UI**

---

## What's New in v2.3.0

### Performance
- **Faster deck icon menus** — Sprite icons are cached in memory, so the deck icon picker and deck dashboards load instantly instead of re-reading/re-scaling sprites on every refresh.
- **Cached icon choices** — The Pokemon icon list is computed once and reused, eliminating repeated directory scans when opening the picker.

### Reliability
- **Fixed numpy/OpenCV crash** — New installs no longer hit the `numpy.dtype size changed` binary incompatibility error during rank detection. numpy is now pinned to `1.26.4`.
- **Complete dependency set** — The installer now also installs the meta-analysis packages (`beautifulsoup4`, `lxml`, `requests`).

### Local-Only Mode (No API Key Required)
- **Works out of the box** — Full monitor, OCR rank/deck detection, overlay, and stats database all work without an OpenAI API key.
- **Clear guidance** — When no API key is present, the app explains local-only mode and guides you through manual deck entry.

### Installer & Build
- **Updated to v2.3** across all scripts, scheduled tasks, and release packaging.
- **Complete release ZIP** — `app_settings.py`, `deck_analytics.py`, and `startup_utils.py` are now bundled.
- **Cleaned up stale references** — Removed outdated v2.1/v2.0 references from launchers and docs.

---

## Installation

### Quick Install (Windows 10/11)

1. **Download** the latest release
2. **Extract** to a permanent location
3. **Right-click** `Installers\INSTALL_COMPLETE_v2.3.bat`
4. Select **"Run as Administrator"**
5. Follow the prompts

The installer will:
- Check/install Python 3.10+
- Check/install Tesseract OCR
- Install all dependencies
- Set up optional OpenAI API key (or use local-only mode)
- ✅ Configure auto-start on login

---

## Features

- **AI-Powered Battle Analysis** — Optional OpenAI GPT-4o deck identification
- **Local-Only Mode** — Full functionality without an API key
- **OCR Rank Detection** — Auto-detects Elo from screen (zero false positives)
- **OCR Deck Detection** — Detects actual deck name from screen
- **Live Overlay UI** — Click-through overlay with league pokeball icons
- **SQLite Database** — Complete battle history with rank progression
- **Modern Stats Dashboard** — Graphs, matchups, meta analysis
- **Automated Battle Log Capture** — Monitors clipboard for battle logs
- **Background Operation** — Runs silently without interrupting gameplay

---

## Requirements

- **Windows 10/11** (required for Win32 features)
- **Python 3.10+** (auto-installed by installer)
- **Tesseract OCR** (auto-installed by installer)
- **OpenAI API Key** (optional — for AI deck detection; local-only mode works without it)

---

## Upgrading from v2.2

1. Extract new v2.3.0 files over existing installation
2. Run `Installers\INSTALL_COMPLETE_v2.3.bat` as Administrator
3. Your database and configuration will be preserved

---

## What's Included

### Core Application
- `TCGLiveMonitor.py` - Main monitoring script
- `AIParseBattleLog.py` - AI battle analyzer
- `BattleDatabase.py` - SQLite database module
- `RankDetector.py` - OCR rank detection
- `OverlayUI.py` - Minimal overlay window
- `StatsUI.py` - Statistics dashboard
- `app_settings.py` - Settings & API key management
- `deck_analytics.py` - Deck analytics helpers
- `startup_utils.py` - Startup/launch helpers

### Installers & Launchers
- `INSTALL_COMPLETE_v2.3.bat` - Main installer
- `Start_GUI_Mode_v2.3.bat` - Quick start
- `Remove_AutoStart_v2.3.bat` - Remove from startup
- `Run_Headless.bat` - Headless launcher
- `Run_TCGLiveMonitor_Command_Prompt.bat` - Console mode

### Utilities
- `AutoRun_Add.py` - Add to Windows startup
- `AutoRun_Remove.py` - Remove from startup
- `AutoClicker.py` - Button automation (beta)
- `SetupStartup.py` - Startup manager GUI

### Documentation
- `README.md` - Main documentation
- `RELEASE_NOTES_v2.3.md` - Comprehensive release notes
- `QUICK_START_v2.0.md` - Quick start guide

---

## Credits

- **OCR:** Powered by Tesseract OCR
- **AI:** Powered by OpenAI GPT-4o
- **UI:** PySide6 (Qt6)
- **Graphs:** matplotlib
- **Icons:** Custom 8-bit Pokeball designs

---

## Support Development

If you enjoy this tool, consider supporting:
**[Buy Me a Coffee](https://www.buymeacoffee.com/lavahawk)**

---

## Help & Support

- **Documentation:** See README.md and QUICK_START_v2.0.md
- **Issues:** [GitHub Issues](https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/issues)
- **Discussions:** [GitHub Discussions](https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/discussions)

---

**Thank you for using Pokemon TCG Live Monitor!**

