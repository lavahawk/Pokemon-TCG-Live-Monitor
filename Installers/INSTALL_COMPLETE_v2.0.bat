@echo off
setlocal enabledelayedexpansion
color 0A
title Pokemon TCG Live Monitor v2.0 - Complete Installation

echo ============================================================
echo    Pokemon TCG Live Monitor v2.0 - Automated Installer
echo ============================================================
echo.
echo Features:
echo  - AI-Powered Battle Analysis
echo  - OCR Rank Detection
echo  - Live Overlay UI with League Icons
echo  - SQLite Database for Statistics
echo  - Auto-Start on Windows Login (No Console)
echo.

REM Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This installer requires Administrator privileges!
    echo Please right-click INSTALL_COMPLETE_v2.0.bat and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)

echo [1/8] Checking Python installation...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] Python not found. Downloading Python 3.10...
    echo Please install Python from the browser window that will open.
    echo IMPORTANT: Check "Add Python to PATH" during installation!
    start https://www.python.org/downloads/
    echo.
    echo Press any key after Python installation is complete...
    pause >nul
    
    REM Verify Python was installed
    python --version >nul 2>&1
    if %errorLevel% neq 0 (
        echo [ERROR] Python still not found. Please install Python and try again.
        pause
        exit /b 1
    )
)
echo [OK] Python is installed
python --version

echo.
echo [2/8] Checking Tesseract OCR installation...
if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo [!] Tesseract OCR not found. Downloading...
    echo Please install Tesseract from the browser window that will open.
    echo Use the default installation path: C:\Program Files\Tesseract-OCR
    start https://github.com/UB-Mannheim/tesseract/wiki
    echo.
    echo Press any key after Tesseract installation is complete...
    pause >nul
    
    if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        echo [ERROR] Tesseract still not found. Please install and try again.
        pause
        exit /b 1
    )
)
echo [OK] Tesseract OCR is installed

echo.
echo [3/8] Creating virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

echo.
echo [4/8] Activating virtual environment...
call .venv\Scripts\activate.bat
echo [OK] Virtual environment activated

echo.
echo [5/8] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo [OK] pip upgraded

echo.
echo [6/8] Installing Python dependencies...
echo This may take a few minutes...
echo.
echo Installing core packages...
pip install psutil==5.9.8 pyperclip==1.8.2 --quiet
pip install pygame==2.5.2 pyfiglet==1.0.2 colorama==0.4.6 --quiet

echo Installing data processing packages...
pip install pandas==2.2.0 pyarrow==22.0.0 --quiet
pip install openpyxl==3.1.2 xlwings==0.30.13 --quiet

echo Installing AI packages...
pip install openai==1.12.0 pydantic==2.6.1 --quiet

echo Installing OCR packages...
pip install opencv-python==4.9.0.80 pytesseract==0.3.10 --quiet
pip install mss==9.0.1 Pillow==10.2.0 pywin32==306 --quiet

echo Installing UI packages...
pip install PySide6==6.10.1 --quiet

if %errorLevel% neq 0 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo [OK] All dependencies installed successfully

echo.
echo [7/8] Setting up OpenAI API key...
if not exist ".env" (
    echo.
    echo ============================================================
    echo    OpenAI API Key Setup
    echo ============================================================
    echo.
    echo To use AI battle log analysis, you need an OpenAI API key.
    echo Get one at: https://platform.openai.com/api-keys
    echo.
    set /p api_key="Enter your OpenAI API Key (or press Enter to skip): "
    
    if "!api_key!"=="" (
        echo.
        echo [SKIPPED] No API key entered. You can add it later to .env file
        echo Format: OPENAI_API_KEY=your_key_here
    ) else (
        echo OPENAI_API_KEY=!api_key! > .env
        echo [OK] API key saved to .env file
    )
) else (
    echo [OK] .env file already exists
)

echo.
echo [8/8] Adding to Windows Task Scheduler for auto-start...
set "SCRIPT_PATH=%CD%\TCGLiveMonitor.py"
set "PYTHON_PATH=%CD%\.venv\Scripts\pythonw.exe"
set "WORKING_DIR=%CD%"

REM Delete existing task if it exists
schtasks /delete /tn "PokemonTCGLiveMonitor_v2" /f >nul 2>&1

REM Create new task - runs at startup, hidden, no console window
schtasks /create /tn "PokemonTCGLiveMonitor_v2" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" /sc onlogon /rl highest /f
if %errorLevel% neq 0 (
    echo [WARNING] Could not create scheduled task. You can run manually.
) else (
    echo [OK] Auto-start task created successfully
)

echo.
echo ============================================================
echo    Installation Complete! v2.0
echo ============================================================
echo.
echo New in v2.0:
echo  [+] Live Overlay UI with League Icons (8-bit Pokeballs)
echo  [+] SQLite Database for fast statistics
echo  [+] Improved OCR rank detection
echo  [+] Higher Elo = Better rank logic
echo  [+] Auto-start with no console window
echo  [+] Complete installer with dependency management
echo.
echo The monitor will start automatically when you log in.
echo It will run hidden in the background with just the overlay visible.
echo.
echo Quick Start:
echo  - To start now: Run Installers\Start_GUI_Mode_v2.0.bat
echo  - To disable auto-start: Run Installers\Remove_AutoStart_v2.0.bat
echo  - See INSTALLATION_GUIDE.md for full documentation
echo.
echo [OK] You can close this window
pause
