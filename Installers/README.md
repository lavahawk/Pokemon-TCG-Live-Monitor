# Pokemon TCG Live Monitor v2.0 - Installers

This folder contains all installation and launcher scripts for v2.0.

## 📦 Installation Files

### INSTALL_COMPLETE_v2.0.bat (Main Installer)
**Right-click → Run as Administrator**

Complete automated installation:
- ✅ Checks/installs Python 3.10+
- ✅ Checks/installs Tesseract OCR
- ✅ Creates virtual environment
- ✅ Installs all dependencies (50+ packages)
- ✅ Prompts for OpenAI API key (saved to `.env`)
- ✅ Adds to Windows Task Scheduler for auto-start
- ✅ Configures GUI mode (no console window)

**Note:** This is the ONLY file users need to run for first-time setup!

---

## 🚀 Launcher Files

### Start_GUI_Mode_v2.0.bat
**Double-click to run**

Starts the monitor manually in GUI mode:
- Uses `pythonw.exe` (no console window)
- Shows only the minimal overlay UI
- Runs in background
- Auto-closes this command window after 3 seconds

Use this when auto-start is disabled or for testing.

---

## 🛑 Utility Files

### Remove_AutoStart_v2.0.bat
**Right-click → Run as Administrator**

Removes the auto-start task from Windows Task Scheduler:
- Deletes "PokemonTCGLiveMonitor_v2" scheduled task
- Monitor will no longer start on login
- Can still run manually with Start_GUI_Mode_v2.0.bat

---

## 🆚 Version 2.0 Changes

All installer files are now versioned and organized:

**v1.x Files (Old):**
- `Install_Dependencies.bat` - Basic dependency installer
- `AutoRun_Add.py` - Python-based auto-start
- `AutoRun_Remove.py` - Python-based removal
- `Run_TCGLiveMonitor_Command_Prompt.bat` - Console mode

**v2.0 Files (New):**
- `INSTALL_COMPLETE_v2.0.bat` - Complete installer with prompts
- `Start_GUI_Mode_v2.0.bat` - GUI mode launcher
- `Remove_AutoStart_v2.0.bat` - Task scheduler removal
- All stored in `Installers/` folder for organization

---

## 📋 What Gets Installed

### System Requirements
- Windows 10/11 (64-bit)
- Python 3.10+ (auto-installed)
- Tesseract OCR 5.5.0+ (auto-installed)

### Python Packages (Auto-installed)
```
# Core (8 packages)
psutil==5.9.8
pyperclip==1.8.2
pygame==2.5.2
pyfiglet==1.0.2
colorama==0.4.6

# Data Processing (4 packages)
pandas==2.2.0
pyarrow==22.0.0
openpyxl==3.1.2
xlwings==0.30.13

# AI (2 packages)
openai==1.12.0
pydantic==2.6.1

# OCR (5 packages)
opencv-python==4.9.0.80
pytesseract==0.3.10
mss==9.0.1
Pillow==10.2.0
pywin32==306

# UI (1 package)
PySide6==6.10.1
```

**Total: 20 packages + dependencies**

---

## 🔐 API Key Management (v2.0)

### New Method (.env file)
The installer prompts for your OpenAI API key and saves it to `.env`:
```
OPENAI_API_KEY=sk-your-key-here
```

### Backwards Compatibility
The script still checks for old `.openai_key` file and environment variables.

**Priority order:**
1. `.env` file (v2.0 preferred)
2. `.openai_key` file (v1.x compatibility)
3. System environment variable `OPENAI_API_KEY`

---

## 🎯 Quick Start

**For new users:**
1. Right-click `INSTALL_COMPLETE_v2.0.bat` → Run as Administrator
2. Follow prompts (install Python + Tesseract if needed)
3. Enter OpenAI API key when prompted
4. Wait for installation to complete
5. Log out and back in (or run `Start_GUI_Mode_v2.0.bat`)
6. Done! Overlay appears when you play Pokemon TCG Live

**For existing v1.x users:**
1. Run `INSTALL_COMPLETE_v2.0.bat` to upgrade
2. Your old API key will be migrated automatically
3. Old task "PokemonTCGLiveMonitor" is replaced with "PokemonTCGLiveMonitor_v2"

---

## 📂 File Locations

After installation:
```
BattleLogImport/
├── Installers/
│   ├── INSTALL_COMPLETE_v2.0.bat       ← Main installer
│   ├── Start_GUI_Mode_v2.0.bat         ← Manual launcher
│   ├── Remove_AutoStart_v2.0.bat       ← Disable auto-start
│   └── README.md                        ← This file
├── .venv/                               ← Virtual environment
│   └── Scripts/
│       └── pythonw.exe                  ← GUI mode Python
├── .env                                 ← OpenAI API key (v2.0)
├── .openai_key                          ← Old API key (v1.x)
├── TCGLiveMonitor.py                   ← Main script
├── OverlayUI.py                        ← Overlay window
├── AIParseBattleLog.py                 ← AI analysis
├── BattleDatabase.py                   ← SQLite database
└── tcg_battles.db                      ← Battle data
```

---

## 🆘 Troubleshooting

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
- Check `.env` file has correct format: `OPENAI_API_KEY=sk-...`
- Verify API key at https://platform.openai.com/api-keys
- Make sure account has credits

**Overlay not showing**
- Start Pokemon TCG Live first
- Then run `Start_GUI_Mode_v2.0.bat`
- Check Task Manager for "pythonw.exe" process
- Make sure game window is titled "Pokémon TCG Live"

**Task Scheduler not working**
- Must run installer as Administrator
- Check Task Scheduler app → "PokemonTCGLiveMonitor_v2"
- Verify task points to correct `.venv\Scripts\pythonw.exe`

---

## 📄 License

Pokemon TCG Live Monitor v2.0
For personal use only.
