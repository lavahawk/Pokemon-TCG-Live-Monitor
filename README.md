# Pokemon TCG Live Monitor v2.3
**AI-Powered Battle Analysis • OCR Rank Detection • Live Overlay UI • Database Statistics**

---

## [Quick Start Guide →](QUICK_START_v2.0.md)

---

## Quick Install (v2.3)

**For first-time setup or upgrade from v2.x:**

1. **Right-click** `Installers\INSTALL_COMPLETE_v2.3.bat`
2. Select **"Run as Administrator"**
3. Follow prompts (Python + Tesseract auto-install if needed)
4. Enter your OpenAI API key when prompted — **or choose Local-Only mode** (no API key needed)
5. **Done!** Auto-starts on login with no console window

See **[Installers/README.md](Installers/README.md)** for full installation guide.

---

## What's New in v2.3

### Performance
- **Faster deck icon menus** — Sprite icons are cached in memory, so the deck icon picker and deck dashboards load instantly.
- **Cached icon choices** — The Pokemon icon list is computed once and reused.

### Reliability
- **Fixed numpy/OpenCV crash** — New installs no longer hit the `numpy.dtype size changed` binary incompatibility error during rank detection. numpy is pinned to `1.26.4`.
- **Complete dependency set** — The installer now also installs the meta-analysis packages.

### Local-Only Mode (No API Key Required)
- **Works out of the box** — Full monitor, OCR rank/deck detection, overlay, and stats database all work without an OpenAI API key.
- **Clear guidance** — When no API key is present, the app explains local-only mode and guides you through manual deck entry.

---

## Features
- **Integrated Overlay UI** - Auto-starts with monitoring, follows game window  
- **League Pokeball Icons** - 8-bit icons change based on Elo tier (Nest/Quick/Poke/Great/Ultra/Master)  
- **Click-Through Overlay** - Won't block gameplay, completely transparent to clicks  
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
- `Installers\INSTALL_COMPLETE_v2.3.bat` - Main installer
- `Installers\Start_GUI_Mode_v2.3.bat` - GUI mode launcher
- `Installers\Remove_AutoStart_v2.3.bat` - Remove from startup
- `Run_Headless.bat` - Headless launcher
- `Run_TCGLiveMonitor_Command_Prompt.bat` - Console mode

### Utilities
- `AutoRun_Add.py` - Add to Windows startup
- `AutoRun_Remove.py` - Remove from startup
- `AutoClicker.py` - Button automation (beta)
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
