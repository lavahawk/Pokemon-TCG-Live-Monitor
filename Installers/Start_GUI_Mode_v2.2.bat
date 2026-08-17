@echo off
title Pokemon TCG Live Monitor v2.2 - GUI Mode

echo ================================================================
echo            Pokemon TCG Live Monitor v2.2
echo                     GUI Mode
echo ================================================================
echo.
echo Starting monitor with visible console output...
echo (Close this window to stop the monitor)
echo.

cd /d "%~dp0\.."

REM Use python.exe (visible console) without --headless so you can see all output
start "Pokemon TCG Live Monitor" .venv\Scripts\python.exe TCGLiveMonitor.py

echo.
echo [OK] Monitor started in GUI mode
echo The overlay will appear when you open Pokemon TCG Live.
echo Click the arrow (^) on the overlay to open Stats Dashboard.
echo.
timeout /t 5
exit
