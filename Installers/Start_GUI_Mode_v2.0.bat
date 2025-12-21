@echo off
title Pokemon TCG Live Monitor v2.0 - GUI Mode

REM Navigate to parent directory
cd /d "%~dp0.."

REM Start the monitor with pythonw.exe (no console window)
start "" ".venv\Scripts\pythonw.exe" "TCGLiveMonitor.py"

echo Pokemon TCG Live Monitor v2.0 started in background!
echo Close this window - the overlay will appear over the game.
timeout /t 3
exit
