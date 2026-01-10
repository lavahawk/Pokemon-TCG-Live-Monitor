@echo off
REM Launch TCG Live Monitor in Headless Mode (No Console)
echo Starting TCG Live Monitor (Headless Mode)...

REM Check if virtual environment exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    .venv\Scripts\pythonw.exe Run_Headless.py
) else (
    echo WARNING: Virtual environment not found
    echo Please run Installers\INSTALL_COMPLETE_v2.1.bat first
    pause
    exit /b 1
)

timeout /t 3
