@echo off
setlocal enabledelayedexpansion
color 0B
title Pokemon TCG Live Monitor v2.3 - Portable Setup

REM ===================================================================
REM Portable setup - does NOT require admin.
REM Downloads Tesseract OCR and Python dependencies locally with fallbacks.
REM ===================================================================
cd /d "%~dp0\.."

cls
echo.
echo     ================================================================
echo                 Pokemon TCG Live Monitor v2.3
echo                     Portable Setup
echo     ================================================================
echo.
echo     This setup downloads the components it needs from the web.
echo     No administrator privileges are required.
echo.
echo     ================================================================
echo.

REM ===================================================================
REM STEP 1: Check Python
REM ===================================================================
echo [1/5] Checking Python installation...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo       [!] Python not detected
    echo.
    echo     Opening Python download page...
    echo     Please download Python 3.10 or later.
    echo     IMPORTANT: Check "Add Python to PATH" during installation.
    echo.
    start https://www.python.org/downloads/
    echo.
    echo     Press any key after Python installation completes...
    pause >nul
    python --version >nul 2>&1
    if %errorLevel% neq 0 (
        color 0C
        echo.
        echo     [ERROR] Python still not detected.
        echo     Please install Python and add it to PATH, then re-run this setup.
        echo.
        pause
        exit /b 1
    )
)
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo       [OK] !PYTHON_VERSION! detected
timeout /t 1 /nobreak >nul

REM ===================================================================
REM STEP 2: Create virtual environment
REM ===================================================================
echo.
echo [2/5] Setting up virtual environment...
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
REM STEP 3: Install Python dependencies (with fallback to requirements.txt)
REM ===================================================================
echo.
echo [3/5] Installing Python dependencies...
echo       This may take a few minutes...
echo.

call .venv\Scripts\activate.bat
if %errorLevel% neq 0 (
    color 0C
    echo       [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)

python -m pip install --upgrade pip --quiet --disable-pip-version-check

echo       - Installing core packages...
pip install psutil==5.9.8 pyperclip==1.8.2 --quiet --disable-pip-version-check
pip install pygame==2.5.2 pyfiglet==1.0.2 colorama==0.4.6 --quiet --disable-pip-version-check

echo       - Installing data processing...
pip install pandas==2.2.0 pyarrow==22.0.0 --quiet --disable-pip-version-check
pip install openpyxl==3.1.2 xlwings==0.30.13 --quiet --disable-pip-version-check

echo       - Installing AI packages...
pip install openai==1.12.0 pydantic==2.6.1 --quiet --disable-pip-version-check

echo       - Installing OCR packages...
pip install numpy==1.26.4 opencv-python==4.9.0.80 pytesseract==0.3.10 --quiet --disable-pip-version-check
pip install mss==9.0.1 Pillow==10.2.0 pywin32==306 --quiet --disable-pip-version-check

echo       - Installing UI packages...
pip install PySide6==6.10.1 matplotlib==3.8.2 --quiet --disable-pip-version-check

echo       - Installing meta analysis packages...
pip install beautifulsoup4>=4.12.0 lxml>=5.0.0 requests>=2.31.0 --quiet --disable-pip-version-check

if %errorLevel% neq 0 (
    echo.
    echo       [WARNING] Some packages failed to install individually.
    echo       Trying requirements.txt as a fallback...
    pip install -r requirements.txt --quiet --disable-pip-version-check
    if %errorLevel% neq 0 (
        color 0C
        echo.
        echo       [ERROR] Failed to install dependencies.
        echo       Please check your internet connection and re-run this setup.
        echo.
        pause
        exit /b 1
    )
)
echo.
echo       [OK] All dependencies installed successfully
timeout /t 1 /nobreak >nul

REM ===================================================================
REM STEP 4: Download Tesseract OCR (portable, no admin) with fallbacks
REM ===================================================================
echo.
echo [4/5] Setting up Tesseract OCR (portable)...
set "TESS_DIR=%CD%\tesseract"
if exist "%TESS_DIR%\tesseract.exe" (
    echo       [OK] Tesseract already present locally
) else (
    echo       Downloading portable Tesseract OCR...
    echo.
    mkdir "%TESS_DIR%" 2>nul

    REM Try multiple mirrors/versions with fallbacks.
    set "TESS_DOWNLOADED="
    powershell -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri 'https://github.com/UB-Mannheim/tesseract/releases/download/v5.5.0.20241111/tesseract-ocr-w64-setup-5.5.0.20241111.exe' -OutFile '%TEMP%\tesseract-setup.exe' -UseBasicParsing; Write-Output 'OK' } catch { Write-Output 'FAIL' }" > "%TEMP%\tess_dl_result.txt"
    set /p TESS_DOWNLOADED=<"%TEMP%\tess_dl_result.txt"

    if "!TESS_DOWNLOADED!"=="OK" (
        echo       [OK] Downloaded Tesseract installer
        echo       Extracting to local folder (no admin needed)...
        "%TEMP%\tesseract-setup.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="%TESS_DIR%"
        timeout /t 5 /nobreak >nul
        del "%TEMP%\tesseract-setup.exe" >nul 2>&1
    ) else (
        echo       [WARNING] Automatic download failed.
        echo       Please download Tesseract manually from:
        echo       https://github.com/UB-Mannheim/tesseract/wiki
        echo       and install it to: %TESS_DIR%
        echo.
        echo       (Or install to C:\Program Files\Tesseract-OCR - the app will find it.)
        echo.
        start https://github.com/UB-Mannheim/tesseract/wiki
    )

    if exist "%TESS_DIR%\tesseract.exe" (
        echo       [OK] Tesseract OCR ready locally
    ) else (
        echo       [WARNING] Tesseract not found locally yet.
        echo       The app will fall back to a system install if present.
    )
)
timeout /t 1 /nobreak >nul

REM ===================================================================
REM STEP 5: Configure startup (registry, no admin needed)
REM ===================================================================
echo.
echo [5/5] Configuring automatic startup (registry, no admin)...
echo.

set "SCRIPT_PATH=%CD%\TCGLiveMonitor.py"
set "PYTHON_PATH=%CD%\.venv\Scripts\pythonw.exe"

REM Remove old scheduled tasks (best-effort, may need admin - ignore errors)
schtasks /delete /tn "PokemonTCGLiveMonitor_v2" /f >nul 2>&1
schtasks /delete /tn "PokemonTCGLiveMonitor_v2.1" /f >nul 2>&1
schtasks /delete /tn "PokemonTCGLiveMonitor_v2.2" /f >nul 2>&1
schtasks /delete /tn "PokemonTCGLiveMonitor_v2.3" /f >nul 2>&1
schtasks /delete /tn "StartTCGLiveMonitor" /f >nul 2>&1
schtasks /delete /tn "PokemonLiveHelper" /f >nul 2>&1

REM Set registry Run key (primary startup method, no admin needed)
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "PokemonTCGLiveMonitor" /t REG_SZ /d "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\" --headless" /f >nul 2>&1
if %errorLevel% equ 0 (
    echo       [OK] Auto-start configured via registry
) else (
    echo       [WARNING] Could not configure auto-start.
    echo       You can run the monitor manually with Run_Headless.bat
)
timeout /t 1 /nobreak >nul

REM ===================================================================
REM Complete
REM ===================================================================
cls
echo.
echo     ================================================================
echo                    Portable Setup Complete! v2.3
echo     ================================================================
echo.
echo     The monitor is installed in:
echo       %CD%
echo.
echo     To start monitoring:
echo       - Run_Headless.bat  (background, no console)
echo       - Run_TCGLiveMonitor_Command_Prompt.bat  (with console)
echo.
echo     To open the Stats Dashboard:
echo       - Run: .venv\Scripts\pythonw.exe StatsUI.py
echo.
echo     NOTE: If Tesseract OCR was not downloaded, rank detection will be
echo     limited until you install it (see Installers\README.md).
echo.
echo     ================================================================
echo.
pause
exit /b 0