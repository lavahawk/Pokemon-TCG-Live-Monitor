# Pokemon TCG Live Monitor v2.0
**AI-Powered Battle Analysis • OCR Rank Detection • Live Overlay UI • Database Statistics**

---

## 📖 [Quick Start Guide →](QUICK_START_v2.0.md)

---

## 🚀 Quick Install (v2.0)

**For first-time setup or upgrade from v1.x:**

1. **Right-click** `Installers\INSTALL_COMPLETE_v2.0.bat`
2. Select **"Run as Administrator"**
3. Follow prompts (Python + Tesseract auto-install if needed)
4. Enter your OpenAI API key when prompted
5. **Done!** Auto-starts on login with no console window

See **[Installers/README.md](Installers/README.md)** for full installation guide.

---

## ✨ What's New in v2.0

### 🎯 Complete Installer System
- **One-click installation** with admin check
- **Auto-installs Python 3.10+** if missing
- **Auto-installs Tesseract OCR** if missing
- **Prompts for API key** during setup (saved to `.env`)
- **Task Scheduler integration** for auto-start on login
- **GUI mode** by default (no console windows)

### 🎨 Live Overlay UI
- **8-bit Pokeball icons** for 6 league tiers (Nest → Master)
- **Click-through window** (doesn't block game)
- **Follows game window** automatically
- **Minimal design** - 156x24px in bottom-right corner
- Shows: `[pokeball] Elo:99 | Max:99 | 0-0`

### 📊 SQLite Database
- **Fast queries** without parsing Excel
- **Complete battle history** with timestamps
- **Rank progression tracking** over time
- **Ready for graphs** and advanced analytics
- **Works when Excel is open** (no permission errors)

### 🔧 Improvements
- **Higher Elo = Better** logic (fixed from v1.x ladder rank)
- **Environment variable** API key support (`.env` file)
- **Organized installers** in separate folder
- **Version numbers** in all scripts
- **Backwards compatible** with v1.x files

## Features
✅ **Integrated Overlay UI** - Auto-starts with monitoring, follows game window  
✅ **League Pokeball Icons** - 8-bit icons change based on Elo tier (Nest/Quick/Poke/Great/Ultra/Master)  
✅ **Click-Through Overlay** - Won't block gameplay, completely transparent to clicks  
✅ **OCR Rank Detection** - Auto-detects Elo from screen (zero false positives!)  
✅ **Max Rank Tracking** - Tracks your highest rank achieved  
✅ **OCR Deck Detection** - Detects actual deck name from screen  
✅ **Automated Battle Log Capture** - Monitors clipboard for Pokemon TCG Live battle logs  
✅ **AI-Powered Analysis** - Uses OpenAI GPT-4o to identify decks and match outcomes  
✅ **Excel Data Export** - Automatically saves results with rank column  
✅ **Background Operation** - Runs silently without interrupting gameplay  
✅ **Sound Notifications** - Plays sound when battle log is detected  

## Quick Start

### 1. Install Dependencies
```batch
Install_Dependencies.bat
```

**Important**: Also install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) for rank detection

### 2. Setup Screen Regions (for rank detection)
```batch
Run_SetupRegions.bat
```
1. Open Pokemon TCG Live to the main menu
2. Click "Detect Game Window"
3. Take a screenshot
4. Select the area where rank appears
5. Save configuration

### 3. Run the Monitor
Use the executable in `BackgroundRun\dist\`:
```
TCGLiveMonitorNOCONSOLE.exe
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
   ↓
5. Results saved to TCGExampleSheet.xlsx
   ↓
6. (Optional) OCR captures rank from screen
```

## Project Structure

### Active Files
- `BackgroundRun\dist\TCGLiveMonitorNOCONSOLE.exe` - Main executable (background mode)
- `BackgroundRun\TCGLiveMonitor.py` - Monitor script (source)
- `AIParseBattleLog.py` - AI parser for battle logs
- `TCGExampleSheet.xlsx` - Data storage

### OCR Features
- `RankDetector.py` - OCR module for screen text detection
- `SetupRegions.py` - Region setup tool
- `Test_RankDetection.py` - Test OCR functionality
- `screen_regions.json` - Region configuration (auto-generated)

### Modern Overlay UI (NEW!)
- `OverlayUI.py` - Modern corner overlay application
- `Start_Overlay.bat` - Easy overlay launcher
- `ViewStats.py` - Quick stats viewer
- `Test_MaxRank.py` - Test rank tracking
- **Documentation:**
  - `OVERLAY_COMPLETE.md` - Full overlay guide
  - `OVERLAY_GUIDE.md` - Quick reference
  - `OVERLAY_DESIGN.md` - Design specifications

### Utilities
- `AutoRun_Add.py` - Add to Windows startup
- `AutoRun_Remove.py` - Remove from startup
- `Create Build Script.bat` - Build with console
- `Create Build Script - NoGUI.bat` - Build without console

### Configuration Files
- `.openai_key` - Your OpenAI API key (auto-created on first run)
- `.user_config` - Your TCG Live username (auto-created)
- `requirements.txt` - Python dependencies

## OCR Rank Detection

See [OCR_README.md](OCR_README.md) for detailed documentation.

**Quick test:**
```batch
Run_TestRankDetection.bat
```

Works in any window position, fullscreen, or resolution.

## Archived Files
Old/redundant files moved to `_Archive\`:
- Old log files
- Duplicate Excel sheets
- Build artifacts
- Testing scripts

## Requirements
- Python 3.8+
- OpenAI API key ([get one here](https://platform.openai.com/api-keys))
- Tesseract OCR ([download](https://github.com/UB-Mannheim/tesseract/wiki))
- Pokemon TCG Live

## Support
For OCR issues, check `OCR_README.md`  
For general issues, check existing battle logs in `BackgroundRun\dist\Logs\`
