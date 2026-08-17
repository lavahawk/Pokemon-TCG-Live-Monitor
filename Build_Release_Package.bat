@echo off
setlocal enabledelayedexpansion
title Build Release Package for Pokemon TCG Live Monitor v2.3.0

echo ================================================================
echo     Pokemon TCG Live Monitor v2.3.0
echo            Release Package Builder
echo ================================================================
echo.

REM Create build directory
echo [1/3] Creating build directory...
if not exist "Installers\Build" mkdir "Installers\Build"
if exist "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0" rmdir /s /q "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0"
mkdir "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0"
echo [OK] Build directory created
echo.

REM Copy production files
echo [2/3] Copying production files...

REM Installers folder FIRST
echo     Copying installers...
mkdir "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\Installers"
copy /Y "Installers\INSTALL_COMPLETE_v2.3.bat"   "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\Installers\" >nul
copy /Y "Installers\Start_GUI_Mode_v2.3.bat"     "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\Installers\" >nul
copy /Y "Installers\Remove_AutoStart_v2.3.bat"   "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\Installers\" >nul
copy /Y "Installers\README.md"                   "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\Installers\" >nul

REM Core Python files
echo     Copying core files...
copy /Y "TCGLiveMonitor.py"   "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "AIParseBattleLog.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "BattleDatabase.py"   "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "RankDetector.py"     "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "OverlayUI.py"        "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "StatsUI.py"          "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "app_settings.py"     "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "deck_analytics.py"   "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "startup_utils.py"    "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul

REM Utilities
echo     Copying utilities...
copy /Y "AutoRun_Add.py"    "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "AutoRun_Remove.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "Run_Headless.py"   "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "AutoClicker.py"    "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "SetupStartup.py"   "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
if exist "SetupStartup.exe" copy /Y "SetupStartup.exe" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul

REM Batch launchers
echo     Copying launchers...
copy /Y "Run_Headless.bat"                      "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "Run_TCGLiveMonitor_Command_Prompt.bat" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "Install_Dependencies.bat"              "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul

REM Configuration and assets
echo     Copying configuration and assets...
copy /Y "requirements.txt"   "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "screen_regions.json" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
if exist "icon.ico" copy /Y "icon.ico" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
if exist "ding.mp3" copy /Y "ding.mp3" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
if exist ".gitignore" copy /Y ".gitignore" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul

REM Documentation
echo     Copying documentation...
copy /Y "README.md"               "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "QUICK_START_v2.0.md"     "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
copy /Y "GITHUB_RELEASE_NOTES.md" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul
if exist "RELEASE_NOTES_v2.3.md" copy /Y "RELEASE_NOTES_v2.3.md" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0\" >nul

echo [OK] All files copied
echo.

REM Create ZIP package
echo [3/3] Creating ZIP package...
cd "Installers\Build"

powershell -Command "Compress-Archive -Path 'Pokemon-TCG-Live-Monitor-v2.3.0\*' -DestinationPath 'Pokemon-TCG-Live-Monitor-v2.3.0.zip' -Force"

if exist "Pokemon-TCG-Live-Monitor-v2.3.0.zip" (
    echo [OK] ZIP package created
) else (
    echo [ERROR] Failed to create ZIP
)

cd ..\..
echo.

echo ================================================================
echo                 BUILD COMPLETE!
echo ================================================================
echo.
echo Release package created:
echo   Location: Installers\Build\
echo   File:     Pokemon-TCG-Live-Monitor-v2.3.0.zip
echo.
echo NEXT STEPS:
echo.
echo 1. Build the EXE installer (Inno Setup):
echo    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer_setup.iss
echo    (or run Build_Inno_Installer.bat)
echo.
echo 2. Upload to GitHub Release:
echo    - Pokemon-TCG-Live-Monitor-v2.3.0.zip
echo    - Pokemon-TCG-Live-Monitor-v2.3.0-Setup.exe
echo.
echo 3. Update release notes (GITHUB_RELEASE_NOTES.md)
echo.
echo ================================================================
echo.
pause
