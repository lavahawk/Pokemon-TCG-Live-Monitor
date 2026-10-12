@echo off
title Pokemon TCG Live Monitor v2.4 - Remove Auto-Start
cd /d "%~dp0\.."
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" AutoRun_Remove.py
echo.
echo To turn auto-start back on later, run: "%PY%" AutoRun_Add.py
pause
