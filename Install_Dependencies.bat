@echo off
REM Re-runs the full setup (Python 3.12 check, .venv, packages, Tesseract) without
REM changing auto-start. Use this after pulling new code that changes requirements.txt.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap_setup.ps1"
pause
