@echo off
title Pokemon TCG Live Monitor v2.4 - Debug Console
cd /d "%~dp0\.."
REM Debug mode: runs the monitor in a visible console (all output is also in Logs\monitor.log).
REM If the auto-started background copy is already running, this one exits immediately -
REM close it first (dashboard > Advanced > Close Application).
if not exist ".venv\Scripts\python.exe" (
    echo The .venv was not found. Run Installers\INSTALL_COMPLETE_v2.4.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" TCGLiveMonitor.py
pause
