@echo off
title Create Portable Installer - Pokemon TCG Live Monitor v2.1.0

echo ================================================================
echo     Pokemon TCG Live Monitor v2.1.0
echo         Portable Installer Creator
echo ================================================================
echo.
echo This will create a single EXE file that users can run to install
echo the application without any manual extraction.
echo.
echo Requirements:
echo   - Python 3.10+
echo   - PyInstaller (will auto-install if needed)
echo.
echo ================================================================
echo.
pause

REM Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Run the portable installer creator
python Create_Portable_Installer.py

pause
