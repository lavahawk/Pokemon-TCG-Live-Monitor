@echo off
title Pokemon TCG Live Monitor v2.0 - GUI Mode

cd /d "%~dp0.."

REM Use python.exe (visible console) without --headless
start "Pokemon TCG Live Monitor" .venv\Scripts\python.exe TCGLiveMonitor.py

echo Pokemon TCG Live Monitor v2.0 started in GUI mode!
echo The overlay will appear when you open Pokemon TCG Live.
timeout /t 3
exit
