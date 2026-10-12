@echo off
setlocal
title Pokemon TCG Live Monitor v2.4 - Installation
cd /d "%~dp0\.."

echo ================================================================
echo              Pokemon TCG Live Monitor v2.4 - Setup
echo ================================================================
echo.
echo This will:
echo   - find (or install) Python 3.12 for your user account
echo   - create the .venv and install all Python packages
echo   - download Tesseract OCR if needed
echo   - start the monitor automatically at Windows login (hidden,
echo     it waits quietly until Pokemon TCG Live is opened)
echo.
echo No administrator rights are needed.
echo.

set "KEYARG="
if not exist ".openai_key" (
    echo Optional: paste your OpenAI API key for AI deck detection,
    echo or just press Enter to use Local-Only mode.
    set /p "API_KEY=OpenAI API key: "
)
if defined API_KEY (
    > ".openai_key" <nul set /p "=%API_KEY%"
    echo [OK] API key saved.
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\bootstrap_setup.ps1" -AutoStart -Launch
if errorlevel 1 (
    echo.
    echo [ERROR] Setup did not finish. See Logs\setup.log for details.
    pause
    exit /b 1
)
echo.
echo [OK] Installation complete. The overlay appears when Pokemon TCG Live is running.
pause
exit /b 0
