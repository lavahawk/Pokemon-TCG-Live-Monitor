@echo off
title Pokemon TCG Live Monitor v2.1 - Console Mode

echo Starting Pokemon TCG Live Monitor...
echo.

REM Check if virtual environment exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    python TCGLiveMonitor.py
) else (
    echo ERROR: Virtual environment not found
    echo Please run Installers\INSTALL_COMPLETE_v2.1.bat first
    echo.
    pause
    exit /b 1
)

pause
