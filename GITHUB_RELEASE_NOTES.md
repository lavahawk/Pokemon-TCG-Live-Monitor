# GitHub Release Notes for v2.1.0

Copy this into the GitHub release page:

---

## Title:
Pokemon TCG Live Monitor v2.1.0 - Production Release

## Description:

# 🎮 Pokemon TCG Live Monitor v2.1.0

**Professional battle tracking system with AI analysis, OCR rank detection, and modern overlay UI**

---

## ✨ What's New in v2.1.0

### 🔧 Professional Installation
- **One-Click Installer** - Automated setup with dependency detection
- **Smart Python Detection** - Auto-downloads Python if missing
- **Tesseract OCR Integration** - Guided installation with links
- **Optional API Key Setup** - Skip or configure during installation
- **Headless by Default** - Runs invisibly in background on startup

### 📊 Enhanced Stats Dashboard
- **Battle Management** - View and delete recent battles
- **Clickable Logs** - Open battle log files directly
- **Confidence Intervals** - Statistical win rate analysis
- **Better Graphs** - Improved date formatting and layout
- **Modern UI** - Glass-morphism design with transparency

### 🎛️ Process & Console Management
- **Console Toggle** - Hide/show console while running
- **Persistent Preferences** - Remember console visibility state
- **Clean Shutdown** - Close entire system from dashboard
- **PID Tracking** - Proper process lifecycle management

### 🤖 AutoClicker System (Beta)
- **Template Matching** - Capture and detect buttons
- **Automated Clicking** - Click buttons when they appear
- **Interactive Setup** - Easy template creation tool

---

## 📦 Installation

### Quick Install (Windows 10/11)

1. **Download** the latest release
2. **Extract** to a permanent location
3. **Right-click** `Installers\INSTALL_COMPLETE_v2.1.bat`
4. Select **"Run as Administrator"**
5. Follow the prompts

The installer will:
- ✅ Check/install Python 3.10+
- ✅ Check/install Tesseract OCR
- ✅ Install all dependencies
- ✅ Prompt for OpenAI API key (optional)
- ✅ Configure auto-start on login

### First Run

After installation:
1. Run `Run_SetupRegions.bat` to configure screen regions
2. Open Pokemon TCG Live to main menu
3. Detect game window and select rank area
4. Monitor starts automatically on next login!

---

## 🚀 Features

✅ **AI-Powered Deck Detection** - GPT-4 identifies decks from battle logs  
✅ **OCR Rank Detection** - Auto-detects Elo from screen  
✅ **SQLite Database** - Fast queries, complete battle history  
✅ **Live Overlay UI** - 8-bit Pokeball icons change with rank  
✅ **Stats Dashboard** - Graphs, win rates, deck usage  
✅ **Headless Operation** - Runs invisibly in background  
✅ **Auto-Start** - Windows Task Scheduler integration  
✅ **Modern UI** - Glass-morphism design with Qt6  

---

## 📋 Requirements

- **Windows 10/11** (required for Win32 features)
- **Python 3.10+** (auto-installed by installer)
- **Tesseract OCR** (auto-installed by installer)
- **OpenAI API Key** (optional - for AI deck detection)

---

## 🔄 Upgrading from v2.0

1. Extract new v2.1.0 files over existing installation
2. Run `Installers\INSTALL_COMPLETE_v2.1.bat` as Administrator
3. Your database and configuration will be preserved

---

## 📁 What's Included

### Core Application (7 files)
- `TCGLiveMonitor.py` - Main monitoring script
- `AIParseBattleLog.py` - AI battle analyzer
- `BattleDatabase.py` - SQLite database module
- `RankDetector.py` - OCR rank detection
- `OverlayUI.py` - Minimal overlay window
- `StatsUI.py` - Statistics dashboard
- `SetupRegions.py` - Screen region setup

### Installers & Launchers
- `INSTALL_COMPLETE_v2.1.bat` - Main installer
- `Start_GUI_Mode_v2.1.bat` - Quick start
- `Remove_AutoStart_v2.1.bat` - Remove from startup
- `Run_Headless.bat` - Headless launcher
- `Run_TCGLiveMonitor_Command_Prompt.bat` - Console mode

### Utilities
- `AutoRun_Add.py` - Add to Windows startup
- `AutoRun_Remove.py` - Remove from startup
- `AutoClicker.py` - Button automation (beta)
- `SetupAutoClicker.py` - Template capture tool (beta)

### Documentation
- `README.md` - Main documentation
- `RELEASE_NOTES_v2.1.md` - Comprehensive release notes
- `QUICK_START_v2.0.md` - Quick start guide

---

## 🐛 Bug Fixes

- Fixed rank update synchronization issues
- Improved console detection from child processes
- Better handling of stale PID files
- Fixed graph rendering edge cases
- Improved error handling throughout

---

## 🙏 Credits

- **OCR:** Powered by Tesseract OCR
- **AI:** Powered by OpenAI GPT-4
- **UI:** PySide6 (Qt6)
- **Graphs:** matplotlib
- **Icons:** Custom 8-bit Pokeball designs

---

## ☕ Support Development

If you enjoy this tool, consider supporting:
**[Buy Me a Coffee](https://www.buymeacoffee.com/lavahawk)** ☕

---

## 📞 Help & Support

- **Documentation:** See README.md and QUICK_START_v2.0.md
- **Issues:** [GitHub Issues](https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/issues)
- **Discussions:** [GitHub Discussions](https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/discussions)

---

## 📊 Changes Summary

- **55 files changed**
- **3,971 insertions**
- **4,949 deletions**
- **Removed 30+ test/debug files**
- **Added 8 new production files**
- **Cleaned and organized codebase**

---

**Thank you for using Pokemon TCG Live Monitor!** 🎮📊

