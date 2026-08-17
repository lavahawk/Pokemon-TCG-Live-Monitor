# Pokemon TCG Live Monitor v2.3 - Installers

This folder contains all installation and launcher scripts for v2.3.

## Installation Files

### INSTALL_COMPLETE_v2.3.bat (Main Installer)
**Right-click → Run as Administrator**

Complete automated installation:
- ✅ Checks/installs Python 3.10+
- Checks/installs Tesseract OCR
- Creates virtual environment
- Installs all dependencies (50+ packages)
- Optional OpenAI API key setup (or Local-Only mode)
- Adds to Windows Task Scheduler for auto-start
- Configures headless mode (no console window)

**Note:** This is the ONLY file users need to run for first-time setup!

---

## Launcher Files

### Start_GUI_Mode_v2.3.bat
**Double-click to run**

Starts the monitor manually with a visible console:
- Uses `python.exe` (shows console output)
- Shows the minimal overlay UI
- Auto-closes this command window after 5 seconds

Use this when auto-start is disabled or for testing.

---

## Utility Files

### Remove_AutoStart_v2.3.bat
**Right-click → Run as Administrator**

Removes the auto-start task from Windows Task Scheduler:
- Deletes "PokemonTCGLiveMonitor_v2.3" scheduled task (and older versions)
- Monitor will no longer start on login
- Can still run manually with Start_GUI_Mode_v2.3.bat

---

## What Gets Installed

### System Requirements
- Windows 10/11 (64-bit)
- Python 3.10+ (auto-installed)
- Tesseract OCR 5.5.0+ (auto-installed)

### Python Packages (Auto-installed)
```
# Core
psutil==5.9.8
pyperclip==1.8.2
pygame==2.5.2
pyfiglet==1.0.2
colorama==0.4.6

# Data Processing
pandas==2.2.0
pyarrow==22.0.0
openpyxl==3.1.2
xlwings==0.30.13

# AI
openai==1.12.0
pydantic==2.6.1

# OCR
numpy==1.26.4
opencv-python==4.9.0.80
pytesseract==0.3.10
mss==9.0.1
Pillow==10.2.0
pywin32==306

# UI
PySide6==6.10.1
matplotlib==3.8.2

# Meta Analysis
beautifulsoup4>=4.12.0
lxml>=5.0.0
requests>=2.31.0
```

**Total: 20+ packages + dependencies**

---

## 🔐 API Key Management

### AI Analysis (Optional)
The installer prompts for your OpenAI API key and saves it to `.openai_key`:
- Enables AI-powered deck identification from battle logs
- Approximate cost: $0.01 per battle analyzed
- Get a key at: https://platform.openai.com/api-keys

### Local-Only Mode (No API Key)
If you skip the API key, the app runs in **Local-Only mode**:
- ✅ Full battle tracking, OCR rank/deck detection, overlay, and stats database
- You manually enter the opponent's deck name after each battle
- No API key or internet required for core functionality

You can add an API key later at any time by creating a `.openai_key` file in the app folder.

---

## Quick Start

**For new users:**
1. Right-click `INSTALL_COMPLETE_v2.3.bat` → Run as Administrator
2. Follow prompts (install Python + Tesseract if needed)
3. Enter OpenAI API key when prompted (or choose Local-Only mode)
4. Wait for installation to complete
5. Log out and back in (or run `Start_GUI_Mode_v2.3.bat`)
6. Done! Overlay appears when you play Pokemon TCG Live

**For existing v2.x users:**
1. Run `INSTALL_COMPLETE_v2.3.bat` to upgrade
2. Your old API key and database will be preserved
3. Old tasks are replaced with "PokemonTCGLiveMonitor_v2.3"

---

## File Locations

After installation:
```
PokemonTCGLiveMonitor/
├── Installers/
│   ├── INSTALL_COMPLETE_v2.3.bat       ← Main installer
│   ├── Start_GUI_Mode_v2.3.bat         ← Manual launcher
│   ├── Remove_AutoStart_v2.3.bat       ← Disable auto-start
│   └── README.md                        ← This file
├── .venv/                               ← Virtual environment
│   └── Scripts/
│       └── pythonw.exe                  ← GUI mode Python
├── .openai_key                          ← OpenAI API key (optional)
├── TCGLiveMonitor.py                   ← Main script
├── OverlayUI.py                        ← Overlay window
├── AIParseBattleLog.py                 ← AI analysis
├── BattleDatabase.py                   ← SQLite database
└── tcg_battles.db                      ← Battle data
```

---

## Troubleshooting

**"This installer requires Administrator privileges"**
- Right-click the .bat file → Run as Administrator

**"Python not found" after installation**
- Make sure you checked "Add Python to PATH" during Python installation
- Close and reopen command prompt
- Try installer again

**"Tesseract not found"**
- Install to default path: `C:\Program Files\Tesseract-OCR`
- Don't change the installation directory

**"OpenAI API Error"**
- Check `.openai_key` file has the correct key
- Verify API key at https://platform.openai.com/api-keys
- Make sure account has credits
- Or switch to Local-Only mode (delete the `.openai_key` file)

**Overlay not showing**
- Start Pokemon TCG Live first
- Then run `Start_GUI_Mode_v2.3.bat`
- Check Task Manager for "pythonw.exe" process
- Make sure game window is titled "Pokémon TCG Live"

**Task Scheduler not working**
- Must run installer as Administrator
- Check Task Scheduler app → "PokemonTCGLiveMonitor_v2.3"
- Verify task points to correct `.venv\Scripts\pythonw.exe`

---

## License

Pokemon TCG Live Monitor v2.0
For personal use only.
