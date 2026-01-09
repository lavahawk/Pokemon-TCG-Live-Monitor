@echo off
title Pokemon TCG Live Monitor v2.1 - Quick Start

echo ================================================================
echo            Pokemon TCG Live Monitor v2.1
echo                    Quick Start
echo ================================================================
echo.
echo Starting monitor in headless mode...
echo (No console window will be shown)
echo.

cd /d "%~dp0\.."
call .venv\Scripts\activate.bat

REM Start in headless mode using pythonw (no console)
start "" .venv\Scripts\pythonw.exe TCGLiveMonitor.py --headless

echo.
echo [OK] Monitor started successfully!
echo.
echo The overlay will appear when you open Pokemon TCG Live.
echo Click the arrow (▲) on the overlay to open the stats dashboard.
echo.
echo To stop the monitor:
echo   - Open Stats Dashboard ^> Advanced ^> Close Application
echo.
timeout /t 5
exit
