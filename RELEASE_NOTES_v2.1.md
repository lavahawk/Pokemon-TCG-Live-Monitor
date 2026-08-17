# Pokemon TCG Live Monitor v2.1 - Release Notes

**Release Date:** January 9, 2026

## Overview

Pokemon TCG Live Monitor v2.1 is a comprehensive battle tracking and statistics system with AI-powered analysis, OCR rank detection, and a modern overlay UI. This release includes major improvements to process management, console control, and battle database functionality.

---

## What's New in v2.1

### Process Management
- **Complete Application Shutdown** - Close entire monitor system from Stats Dashboard
- **PID File System** - Track and manage monitor process across UI components
- **Headless Mode Support** - Run without console window using `Run_Headless.bat`
- **Command-Line Arguments** - `--headless` and `--no-overlay` flags for flexible operation

### Console Management
- **Console Visibility Toggle** - Hide/show console window while monitor runs
- **Persistent Preferences** - Console state saved and restored across sessions
- **Smart Detection** - Automatically finds monitor console even when launched from child process
- **Cross-Process Control** - Stats UI can control monitor's console window

### Enhanced Stats Dashboard
- **Battle Management** - View and delete recent battles (last 20)
- **Clickable Battle Logs** - Click any battle to open its log file
- **Improved Graphs** - Better date formatting and tick spacing
- **Confidence Intervals** - Win rate stats now show 95% confidence intervals for decks with 3+ games
- **Advanced Tab** - New settings, debugging tools, and AutoRun management

### Overlay Improvements
- **Clickable Arrow** - Toggle stats dashboard with small arrow button (▲/▼)
- **Smart Stats Updates** - Database queries for faster W/L tracking
- **Version Display** - Shows v2.1 in overlay title

### Database Enhancements
- **Automatic Rank Updates** - Most recent battle updated with detected rank
- **Session Stats Sync** - Deleting battles updates session statistics
- **Better Data Integrity** - Improved error handling and transaction management

### New Tools & Scripts
- **AutoClicker Module** - Template-based button clicking for automation
- **SetupAutoClicker.py** - Interactive tool to capture button templates
- **Run_Headless.py/.bat** - Launch monitor without console
- **Test Scripts** - Console detection, preference testing, and validation tools

---

## Installation

### Quick Install (Recommended)

1. **Download and Extract**
   - Download `Pokemon-TCG-Live-Monitor-v2.1.zip`
   - Extract to a permanent location (e.g., `C:\TCGLiveMonitor`)

2. **Run Installer** (Admin Required)
   ```batch
   Right-click → Run as Administrator:
   Installers\INSTALL_COMPLETE_v2.0.bat
   ```
   - Auto-installs Python 3.10+ if missing
   - Auto-installs Tesseract OCR if missing
   - Prompts for OpenAI API key
   - Sets up Windows Task Scheduler auto-start

3. **Initial Setup**
   ```batch
   Run_SetupRegions.bat
   ```
   - Open Pokemon TCG Live to main menu
   - Click "Detect Game Window"
   - Select rank display region
   - Save configuration

4. **Start Monitoring**
   ```batch
   Run_Headless.bat          (No console - silent mode)
   OR
   Run_TCGLiveMonitor_Command_Prompt.bat  (With console - debug mode)
   ```

### Manual Installation

1. **Install Dependencies**
   ```batch
   pip install -r requirements.txt
   ```

2. **Install Tesseract OCR**
   - Download from: https://github.com/UB-Mannheim/tesseract/wiki
   - Install to default location: `C:\Program Files\Tesseract-OCR\`

3. **Configure Environment**
   - Create `.env` file or `.openai_key` file with your OpenAI API key
   - Run `SetupRegions.py` to configure screen regions

---

## Usage

### Starting the Monitor

**Headless Mode (Recommended for Daily Use)**
```batch
Run_Headless.bat
```
- No console window
- Overlay and stats UI only
- Perfect for Windows Startup

**Console Mode (Debug/Development)**
```batch
Run_TCGLiveMonitor_Command_Prompt.bat
```
- See all log messages
- Can hide console via Stats UI Advanced tab
- Better for troubleshooting

### Accessing Stats Dashboard

1. **Click the small overlay** (bottom-right corner of game window)
2. **Click the arrow (▲)** to expand stats dashboard
3. View graphs, deck usage, recent battles, and more

### Managing Console Window

1. Open Stats Dashboard → **Advanced** tab
2. **Debugging & Development** section
3. Click **"Hide Console Window"** to run headless
4. Preference saved - console stays hidden on next launch

### Stopping the Monitor

**Method 1: Stats Dashboard (Recommended)**
- Advanced tab → Application Control → **"Close Application"**

**Method 2: Task Manager**
- End `python.exe` process running TCGLiveMonitor

---

## Features

### Core Monitoring
- **Automated Battle Log Capture** - Monitors clipboard for battle logs  
- **AI-Powered Deck Detection** - GPT-4 identifies decks from battle logs  
- **OCR Rank Detection** - Auto-detects Elo from screen (zero config after setup)  
- **SQLite Database** - Fast queries, complete battle history  
- **Excel Export** - Compatible with v1.x Excel sheets  
- **Sound Notifications** - Plays sound when battle detected  

### Overlay UI
- **8-bit Pokeball Icons** - Changes based on Elo tier (Nest/Quick/Poke/Great/Ultra/Master)  
- **Click-Through Window** - Won't block gameplay  
- **Auto-Follows Game** - Stays positioned in game window  
- **Minimal Design** - 170x24px display with real-time stats  
- **Expandable Dashboard** - Click arrow to open full stats  

### Stats Dashboard
- **Elo Progression Graph** - Track your rank over time (last 50 updates)  
- **Win Rate Trend Graph** - Daily win rates for past 30 days  
- **Deck Usage Statistics** - Most-played decks with win rates and confidence intervals  
- **Recent Battles List** - Last 10 battles with clickable log files  
- **Battle Management** - Delete incorrect/duplicate battles  
- **Limitless TCG Integration** - Quick access to play.limitlesstcg.com  
- **Modern Glass-Morphism UI** - Transparent, sleek design  

### Advanced Features
- **AutoRun Configuration** - Add/remove from Windows Startup  
- **Process Management** - Full control over monitor lifecycle  
- **Console Toggle** - Hide/show console while running  
- **Headless Operation** - Run completely in background  
- **Debug Tools** - OCR test window, AI parser access  
- **Battle Log Archive** - All logs saved with timestamps  

---

## Requirements

### Software
- **Windows 10/11** (required for Win32 API features)
- **Python 3.10+** (auto-installed by installer)
- **Tesseract OCR** (auto-installed by installer)
- **OpenAI API Key** (for deck detection)

### Python Packages
See `requirements.txt` for complete list:
- `psutil` - Process management
- `pyperclip` - Clipboard monitoring
- `pygame` - Sound notifications
- `pandas` - Data processing
- `openpyxl` - Excel export
- `openai` - AI deck detection
- `opencv-python` - OCR image processing
- `pytesseract` - OCR text extraction
- `mss` - Screen capture
- `PySide6` - Modern Qt6 UI
- `matplotlib` - Graph rendering
- `pywin32` - Windows API access

---

## Project Structure

```
BattleLogImport/
├── TCGLiveMonitor.py              # Main monitoring script (v2.1)
├── AIParseBattleLog.py            # AI battle log parser
├── BattleDatabase.py              # SQLite database module
├── RankDetector.py                # OCR rank detection
├── OverlayUI.py                   # Minimal overlay window (v2.1)
├── StatsUI.py                     # Stats dashboard (v2.1)
├── AutoClicker.py                 # NEW - Button automation
├── SetupRegions.py                # Screen region configuration
├── SetupAutoClicker.py            # NEW - Button template capture
├── Run_Headless.py                # NEW - Headless launcher
├── Run_Headless.bat               # NEW - Headless batch launcher
├── requirements.txt               # Python dependencies
├── screen_regions.json            # OCR region configuration
├── tcg_battles.db                 # SQLite battle database
├── TCGExampleSheet.xlsx           # Excel data export
├── .openai_key                    # OpenAI API key (created by installer)
├── .user_config                   # Username configuration
├── .monitor_pid                   # NEW - Process ID tracking
├── .console_pref                  # NEW - Console visibility preference
├── Installers/                    # Complete installer package
│   ├── INSTALL_COMPLETE_v2.0.bat
│   ├── Start_GUI_Mode_v2.0.bat
│   └── Remove_AutoStart_v2.0.bat
├── Logs/                          # Battle log archives
├── BackgroundRun/                 # Compiled executables (legacy)
├── Testing New Stuff/             # Experimental features
└── _Archive/                      # Old/redundant files
```

---

## Known Issues

### Windows-Specific
- Console management requires Windows (uses Win32 API)
- Some antivirus software may flag Python executables

### OCR Detection
- Requires Tesseract OCR to be installed
- Screen regions must be calibrated per resolution
- Game window must be visible (not minimized)

### AI Deck Detection
- Requires OpenAI API key (costs ~$0.01 per battle)
- Accuracy depends on cards played in battle log
- Confidence score indicates reliability

---

## Migration from v2.0

### Automatic Migration
- v2.1 is fully backwards compatible with v2.0
- Existing database, config files, and Excel sheets work unchanged
- No manual migration needed

### New Features to Configure
1. **Console Preference** - Will default to visible, can hide via Stats UI
2. **PID File** - Auto-created on monitor start
3. **Battle Management** - Access via Advanced tab in Stats UI

---

## Contributing

This is an open-source project. Contributions welcome!

### Reporting Issues
- Use GitHub Issues for bug reports
- Include logs from `Logs/` directory
- Specify your Windows version and Python version

### Feature Requests
- Open GitHub Issue with "Feature Request" label
- Describe use case and expected behavior

---

## License

This project is open source. See LICENSE file for details.

---

## Support Development

If you enjoy using this tool, consider supporting development:

**Buy Me a Coffee:** https://www.buymeacoffee.com/lavahawk

---

## Contact

- **GitHub:** https://github.com/lavahawk/Pokemon-TCG-Live-Monitor
- **Issues:** https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/issues

---

## Credits

- **OCR:** Powered by Tesseract OCR
- **AI Analysis:** Powered by OpenAI GPT-4
- **UI Framework:** PySide6 (Qt6)
- **Graphs:** matplotlib
- **Icons:** Custom 8-bit Pokeball designs

---

## Changelog

### v2.1 (2026-01-09)
- Added complete process management system
- Added console visibility toggle with persistence
- Added headless mode launcher
- Enhanced Stats Dashboard with battle management
- Improved database integration and error handling
- Added AutoClicker module for automation
- Added comprehensive test suite
- Fixed rank update issues
- Improved graph date formatting

### v2.0 (Previous Release)
- Added OCR rank detection
- Added SQLite database
- Added overlay UI with Pokeball icons
- Added stats dashboard with graphs
- Added one-click installer
- Database integration for battle tracking

### v1.x (Legacy)
- Basic clipboard monitoring
- AI deck detection
- Excel export only

---

**Thank you for using Pokemon TCG Live Monitor!** (≧▽≦)
