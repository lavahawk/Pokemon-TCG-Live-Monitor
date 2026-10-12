@echo off
setlocal
title Build Release Package - Pokemon TCG Live Monitor v2.4.0
cd /d "%~dp0"
REM Builds Installers\Build\Pokemon-TCG-Live-Monitor-v2.4.0.zip from release_manifest.txt
REM (the single list of shipped files used by every installer builder).
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" Create_Portable_Installer.py --zip-only
if errorlevel 1 (
    echo [ERROR] Release ZIP could not be built - a file in release_manifest.txt is missing.
    exit /b 1
)
echo [OK] Release ZIP built.
