@echo off
setlocal enabledelayedexpansion
color 0B
title Pokemon TCG Live Monitor v2.1 - Professional Installation

REM ===================================================================
REM Change to parent directory (where the main files are)
REM ===================================================================
cd /d "%~dp0\.."

cls
echo.
echo     ================================================================
echo                 Pokemon TCG Live Monitor v2.1
echo                    Professional Installation
echo     ================================================================
echo.
echo     Features:
echo       [+] AI-Powered Battle Analysis (Optional)
echo       [+] OCR Rank Detection
echo       [+] Live Overlay UI with League Icons
echo       [+] SQLite Database Statistics
echo       [+] Automatic Headless Startup
echo       [+] Modern Stats Dashboard
echo.
echo     ================================================================
echo.

REM ===================================================================
REM STEP 1: Check for Administrator Privileges
REM ===================================================================
echo [1/9] Checking administrator privileges...
net session >nul 2>&1
if %errorLevel% neq 0 (
    color 0C
    echo.
    echo     [ERROR] Administrator privileges required!
    echo.
    echo     Please right-click this file and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)
echo       [OK] Running as Administrator
timeout /t 1 /nobreak >nul

REM ===================================================================
REM STEP 2: Check Python Installation
REM ===================================================================
echo.
echo [2/9] Checking Python installation...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo       [!] Python not detected
    echo.
    echo     Opening Python download page...
    echo     Please download Python 3.10 or later
    echo.
    echo     IMPORTANT: During installation, check "Add Python to PATH"
    echo.
    start https://www.python.org/downloads/
    echo.
    echo     Press any key after Python installation completes...
    pause >nul
    
    REM Verify Python installation
    python --version >nul 2>&1
    if %errorLevel% neq 0 (
        color 0C
        echo.
        echo     [ERROR] Python still not detected
        echo     Please ensure Python is installed and added to PATH
        echo.
        pause
        exit /b 1
    )
)
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo       [OK] !PYTHON_VERSION! detected
timeout /t 1 /nobreak >nul

REM ===================================================================
REM STEP 3: Check Tesseract OCR
REM ===================================================================
echo.
echo [3/9] Checking Tesseract OCR installation...
if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo       [!] Tesseract OCR not detected
    echo.
    echo     Downloading Tesseract OCR installer...
    echo.
    
    REM Download Tesseract installer to temp directory
    set "TESSERACT_INSTALLER=%TEMP%\tesseract-ocr-setup.exe"
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe' -OutFile '%TESSERACT_INSTALLER%' -UseBasicParsing}"
    
    if exist "%TESSERACT_INSTALLER%" (
        echo       [OK] Download complete
        echo.
        echo     Installing Tesseract OCR...
        echo     (This will open the installer - please follow the prompts)
        echo.
        
        REM Run installer silently with default settings
        start /wait "" "%TESSERACT_INSTALLER%" /S /D=C:\Program Files\Tesseract-OCR
        
        REM Clean up installer
        del "%TESSERACT_INSTALLER%" >nul 2>&1
        
        REM Verify installation
        timeout /t 2 /nobreak >nul
        if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
            color 0C
            echo.
            echo     [ERROR] Tesseract OCR installation failed
            echo     Please install manually from: https://github.com/UB-Mannheim/tesseract/wiki
            echo.
            pause
            exit /b 1
        )
        echo       [OK] Tesseract OCR installed successfully
    ) else (
        color 0C
        echo.
        echo     [ERROR] Failed to download Tesseract installer
        echo     Please install manually from: https://github.com/UB-Mannheim/tesseract/wiki
        echo.
        pause
        exit /b 1
    )
) else (
    echo       [OK] Tesseract OCR already installed
)
timeout /t 1 /nobreak >nul

REM ===================================================================
REM STEP 4: Create Virtual Environment
REM ===================================================================
echo.
echo [4/9] Setting up virtual environment...
if not exist ".venv" (
    echo       Creating new virtual environment...
    python -m venv .venv
    if %errorLevel% neq 0 (
        color 0C
        echo       [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo       [OK] Virtual environment created
) else (
    echo       [OK] Virtual environment already exists
)
timeout /t 1 /nobreak >nul

REM ===================================================================
REM STEP 5: Activate Virtual Environment
REM ===================================================================
echo.
echo [5/9] Activating virtual environment...
call .venv\Scripts\activate.bat
if %errorLevel% neq 0 (
    color 0C
    echo       [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo       [OK] Virtual environment activated
timeout /t 1 /nobreak >nul

REM ===================================================================
REM STEP 6: Upgrade pip
REM ===================================================================
echo.
echo [6/9] Upgrading pip package manager...
python -m pip install --upgrade pip --quiet --disable-pip-version-check
echo       [OK] pip upgraded
timeout /t 1 /nobreak >nul

REM ===================================================================
REM STEP 7: Install Python Dependencies
REM ===================================================================
echo.
echo [7/9] Installing Python dependencies...
echo       This may take a few minutes...
echo.

echo       - Installing core packages...
pip install psutil==5.9.8 pyperclip==1.8.2 --quiet --disable-pip-version-check
pip install pygame==2.5.2 pyfiglet==1.0.2 colorama==0.4.6 --quiet --disable-pip-version-check

echo       - Installing data processing...
pip install pandas==2.2.0 pyarrow==22.0.0 --quiet --disable-pip-version-check
pip install openpyxl==3.1.2 xlwings==0.30.13 --quiet --disable-pip-version-check

echo       - Installing AI packages...
pip install openai==1.12.0 pydantic==2.6.1 --quiet --disable-pip-version-check

echo       - Installing OCR packages...
pip install opencv-python==4.9.0.80 pytesseract==0.3.10 --quiet --disable-pip-version-check
pip install mss==9.0.1 Pillow==10.2.0 pywin32==306 --quiet --disable-pip-version-check

echo       - Installing UI packages...
pip install PySide6==6.10.1 matplotlib==3.8.2 --quiet --disable-pip-version-check

if %errorLevel% neq 0 (
    color 0C
    echo.
    echo       [ERROR] Failed to install dependencies
    echo       Please check your internet connection
    pause
    exit /b 1
)
echo.
echo       [OK] All dependencies installed successfully
timeout /t 1 /nobreak >nul

REM ===================================================================
REM STEP 8: OpenAI API Key Setup (Optional)
REM ===================================================================
echo.
echo [8/9] OpenAI API Key Setup (Optional)...
echo.
echo     ================================================================
echo                       AI Battle Analysis Setup
echo     ================================================================
echo.
echo     The AI battle analyzer uses OpenAI's GPT to identify decks.
echo.
echo     Options:
echo       1. Enter API key now  (Recommended - enables AI analysis)
echo       2. Skip for now       (Can add later in Stats Dashboard)
echo.
echo     Get your API key: https://platform.openai.com/api-keys
echo     Approximate cost: $0.01 per battle
echo.
echo     ================================================================
echo.

if exist ".openai_key" (
    echo       [OK] API key already configured
    echo.
) else (
    set /p "api_choice=Enter choice (1 or 2): "
    
    if "!api_choice!"=="1" (
        echo.
        set /p "api_key=Paste your OpenAI API Key: "
        
        if "!api_key!"=="" (
            echo       [SKIPPED] No key entered
        ) else (
            echo !api_key! > .openai_key
            echo       [OK] API key saved
            echo       AI battle analysis enabled
        )
    ) else (
        echo       [SKIPPED] AI analysis disabled
        echo       You can add your API key later in Stats Dashboard
    )
)
timeout /t 2 /nobreak >nul

REM ===================================================================
REM STEP 9: Windows Startup Configuration
REM ===================================================================
echo.
echo [9/9] Configuring automatic startup...
echo.

set "SCRIPT_PATH=%CD%\TCGLiveMonitor.py"
set "PYTHON_PATH=%CD%\.venv\Scripts\pythonw.exe"
set "WORKING_DIR=%CD%"

REM Delete old task if exists
schtasks /delete /tn "PokemonTCGLiveMonitor_v2" /f >nul 2>&1
schtasks /delete /tn "PokemonTCGLiveMonitor_v2.1" /f >nul 2>&1

REM Create scheduled task for headless startup
schtasks /create /tn "PokemonTCGLiveMonitor_v2.1" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\" --headless" /sc onlogon /rl highest /f >nul 2>&1

if %errorLevel% neq 0 (
    echo       [WARNING] Could not create startup task
    echo       You can run the monitor manually
) else (
    echo       [OK] Auto-start configured (headless mode)
    echo       Monitor will start automatically on login
)
timeout /t 2 /nobreak >nul

REM ===================================================================
REM Installation Complete
REM ===================================================================
cls
echo.
echo     ================================================================
echo                    Installation Complete! v2.1
echo     ================================================================
echo.
echo     What's New in v2.1:
echo       [+] Headless mode by default (no console window)
echo       [+] Enhanced stats dashboard with battle management
echo       [+] Console visibility toggle
echo       [+] Improved process management
echo       [+] Better database integration
echo       [+] Modern glass-morphism UI
echo.
echo     ================================================================
echo                         Quick Start Guide
echo     ================================================================
echo.
echo     STEP 1: Start Monitoring
echo       Option A: Auto-Start (Default)
echo         - Monitor starts automatically on login
echo         - Runs in background (headless mode)
echo.
echo       Option B: Manual Start
echo         - Headless: Run_Headless.bat
echo         - With Console: Run_TCGLiveMonitor_Command_Prompt.bat
echo.
echo     STEP 2: Access Stats
echo       - Click the small overlay arrow (▲) in-game
echo       - Or double-click: Installers\Start_GUI_Mode_v2.1.bat
echo.
echo     NOTE: OCR screen regions are pre-configured for standard
echo           1920x1080 displays. The overlay will automatically
echo           adjust to your screen resolution.
echo.
echo     ================================================================
echo                         Useful Commands
echo     ================================================================
echo.
echo     Open Stats Dashboard:  Installers\Start_GUI_Mode_v2.1.bat
echo     Remove from Startup:   Installers\Remove_AutoStart_v2.1.bat
echo     Add to Startup:        Installers\Start_GUI_Mode_v2.1.bat
echo.
echo     ================================================================
echo                         Getting Help
echo     ================================================================
echo.
echo     Documentation:
echo       - README.md
echo       - QUICK_START_v2.0.md
echo       - RELEASE_NOTES_v2.1.md
echo.
echo     GitHub: https://github.com/lavahawk/Pokemon-TCG-Live-Monitor
echo     Support: Buy me a coffee at https://buymeacoffee.com/lavahawk
echo.
echo     ================================================================
echo.
echo     The monitor will start automatically next time you log in.
echo     The overlay will appear when Pokemon TCG Live is detected.
echo.
echo     ================================================================
echo.
pause
exit /b 0
