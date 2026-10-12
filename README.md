# Pokemon TCG Live Monitor v2.4
**AI-Powered Battle Analysis • OCR Rank Detection • Live Overlay UI • Database Statistics**

---

## [Quick Start Guide →](QUICK_START_v2.0.md)

---

## Quick Install (v2.4)

**Option A: installer:** run `Pokemon-TCG-Live-Monitor-v2.4.0-Setup.exe` from the Releases page. No admin rights are needed.

**Option B: from the source folder:** double-click `Installers\INSTALL_COMPLETE_v2.4.bat`. You don't need to run it as Administrator.

Either way, setup:
1. Finds Python 3.10–3.12, or installs Python 3.12 for your user if none is found.
2. Creates `.venv` and installs the packages, then downloads Tesseract OCR if needed.
3. Asks for an optional OpenAI API key. Leave it empty for Local-Only mode.
4. Registers auto-start: the monitor starts hidden at login, waits quietly until Pokemon TCG Live opens, then shows the overlay.

**Debug mode:** run `Run_TCGLiveMonitor_Command_Prompt.bat` to see live output in a console. Everything is also written to `Logs\monitor.log`. Auto-export events go to `Logs\autoclicker.log`.

**After pulling new code** that changes `requirements.txt`, run `Install_Dependencies.bat`.

See **[RELEASE_NOTES_v2.4.md](RELEASE_NOTES_v2.4.md)** for what changed, and `DevVault/` (open it as an Obsidian vault) for architecture, process maps and the bug register.

---

## Features
- **Integrated Overlay UI** - Auto-starts with monitoring, follows game window  
- **League Pokeball Icons** - 8-bit icons change based on Elo tier (Nest/Quick/Poke/Great/Ultra/Master)  
- **OCR Rank Detection** - Auto-detects Elo from screen (zero false positives!)  
- **Max Rank Tracking** - Tracks your highest rank achieved  
- **OCR Deck Detection** - Detects actual deck name from screen  
- **Automated Battle Log Capture** - Monitors clipboard for Pokemon TCG Live battle logs  
- **AI-Powered Analysis** - Uses OpenAI GPT-4o to identify decks and match outcomes (optional)  
- **Local-Only Mode** - Full functionality without an API key  
- **SQLite Database** - Complete battle history with rank progression  
- **Modern Stats Dashboard** - Graphs, matchups, meta analysis  
- **Background Operation** - Runs silently without interrupting gameplay  
- **Sound Notifications** - Plays sound when battle log is detected  

## Quick Start

### 1. Install Dependencies
```batch
Install_Dependencies.bat
```

**Important**: Also install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) for rank detection

### 2. Run the Monitor
```batch
Run_TCGLiveMonitor_Command_Prompt.bat
```
Or run in the background (headless):
```batch
Run_Headless.bat
```

Or add to Windows startup using `AutoRun_Add.py`

## How It Works

```
1. Monitor detects Pokemon TCG Live is running
   ↓
2. Watches clipboard for battle logs
   ↓
3. When log detected → saves to file + plays sound
   ↓
4. AI analyzes: your deck, opponent deck, win/loss, confidence
   (or Local-Only mode: you enter the opponent deck manually)
   ↓
5. Results saved to SQLite database + Excel
   ↓
6. OCR captures rank and deck from screen
```

## Project Structure

### Core Files
- `TCGLiveMonitor.py` - Main monitoring script
- `AIParseBattleLog.py` - AI/local battle log parser
- `BattleDatabase.py` - SQLite database module
- `RankDetector.py` - OCR module for screen text detection
- `OverlayUI.py` - Modern corner overlay application
- `StatsUI.py` - Statistics dashboard
- `app_settings.py` - Settings & API key management
- `deck_analytics.py` - Deck analytics helpers
- `startup_utils.py` - Startup/launch helpers

### Installers & Launchers
- `Installers\INSTALL_COMPLETE_v2.4.bat` - Main installer (calls `bootstrap_setup.ps1`)
- `Installers\Start_GUI_Mode_v2.4.bat` - Debug console launcher
- `Installers\Remove_AutoStart_v2.4.bat` - Remove from startup
- `Run_Headless.bat` - Headless launcher
- `Run_TCGLiveMonitor_Command_Prompt.bat` - Console mode

### Utilities
- `AutoRun_Add.py` - Add to Windows startup
- `AutoRun_Remove.py` - Remove from startup
- `BattleEndAutomation.py` + `AutoClicker.py` - Battle-end auto-export (BATTLE LOG → export)
- `game_window.py` - Shared game-window lookup
- `leagues.py` - Ladder league thresholds
- `SetupStartup.py` - Startup manager GUI

### Configuration Files
- `.openai_key` - Your OpenAI API key (optional, auto-created)
- `.user_config` - Your TCG Live username (auto-created)
- `screen_regions.json` - OCR region configuration (pre-configured)
- `requirements.txt` - Python dependencies

## Requirements
- Windows 10/11
- Python 3.10+
- Tesseract OCR ([download](https://github.com/UB-Mannheim/tesseract/wiki))
- Pokemon TCG Live
- OpenAI API key (optional — for AI deck detection)

## Support
For general issues, check the battle logs in `Logs\`  
For feature requests or bug reports, open an issue on [GitHub](https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/issues)
