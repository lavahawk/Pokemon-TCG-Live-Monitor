# Pokemon TCG Live Monitor v2.4
**AI-Powered Battle Analysis • OCR Rank Detection • Live Overlay UI • Database Statistics**

---

## [Quick Start Guide →](QUICK_START_v2.0.md)

---

## Quick Install (v2.4)

Download **`PokemonTCGLiveMonitor-2.4.0-Setup.exe`** from the [Releases page](https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/releases/latest) and run it.

- Everything is included (its own Python runtime, all packages, Tesseract OCR). Nothing is downloaded during setup, and no admin rights are needed.
- Setup optionally asks for your TCG Live username and an OpenAI API key (leave it empty for Local-Only mode).
- With auto-start ticked, the monitor starts hidden at login, waits quietly until Pokemon TCG Live opens, then shows the overlay.
- Upgrading keeps your battle history and settings.

If Windows SmartScreen warns about an unrecognised app, click **More info → Run anyway** (the installer isn't code-signed).

**Debug mode:** Start menu → Pokemon TCG Live Monitor → Tools → *Monitor (debug console)*. Everything is also written to `Logs\monitor.log`. Auto-export events go to `Logs\autoclicker.log`.

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

## Running from source (developers)

1. `Install_Dependencies.bat` creates `.venv` with Python 3.10–3.12 and installs `requirements.txt`.
2. Install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki), or copy a `tesseract\` folder next to the code.
3. `Run_TCGLiveMonitor_Command_Prompt.bat` runs the monitor with a console.

### Building the installer
```
powershell -NoProfile -ExecutionPolicy Bypass -File installer\build_installer.ps1
```
Needs Inno Setup 6 and Tesseract on the build machine. It produces `installer\Output\PokemonTCGLiveMonitor-<version>-Setup.exe` plus a `.sha256` file. The version comes from `version.py`, and the shipped files are listed in `release_manifest.txt`. The build smoke-tests the bundled runtime before compiling.

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

### Installer & Launchers
- `installer\` - Installer build (`build_installer.ps1`, Inno Setup script, smoke test, wizard artwork)
- `release_manifest.txt` - Files shipped in the installer
- `version.py` - App version (single source)
- `Run_TCGLiveMonitor_Command_Prompt.bat` - Console mode (source checkout)
- `Install_Dependencies.bat` - Developer setup (.venv)

### Utilities
- `BattleEndAutomation.py` + `AutoClicker.py` - Battle-end auto-export (BATTLE LOG → export)
- `BattleState.py` - In-battle detection (settings-gear template)
- `SetupAutoClicker.py` - Recapture the auto-export button images
- `game_window.py` - Shared game-window lookup
- `leagues.py` - Ladder league thresholds
- `qt_dialogs.py` - Small Qt prompts

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
