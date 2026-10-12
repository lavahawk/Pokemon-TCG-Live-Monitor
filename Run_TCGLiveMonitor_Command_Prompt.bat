@echo off
title PTCGL Monitor Console
cd /d "%~dp0"
REM Debug mode: visible console. Output is also written to Logs\monitor.log.
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found.
    echo Please run Installers\INSTALL_COMPLETE_v2.4.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" TCGLiveMonitor.py
pause
