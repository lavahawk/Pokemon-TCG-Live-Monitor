@echo off
setlocal enabledelayedexpansion
title Build Release Package for Pokemon TCG Live Monitor v2.1.0

echo ================================================================
echo     Pokemon TCG Live Monitor v2.1.0
echo            Release Package Builder
echo ================================================================
echo.

REM Create build directory
echo [1/3] Creating build directory...
if not exist "Installers\Build" mkdir "Installers\Build"
if exist "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0" rmdir /s /q "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0"
mkdir "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0"
echo [OK] Build directory created
echo.

REM Copy production files
echo [2/3] Copying production files...

REM Installers folder FIRST (so it appears first in ZIP)
echo     Copying installers...
mkdir "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\Installers"
copy /Y "Installers\*.bat" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\Installers\" >nul
copy /Y "Installers\README.md" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\Installers\" >nul

REM Core Python files
echo     Copying core files...
copy /Y "TCGLiveMonitor.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "AIParseBattleLog.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "BattleDatabase.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "RankDetector.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "OverlayUI.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "StatsUI.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul

REM Utilities (NO SetupRegions - regions are pre-configured)
echo     Copying utilities...
copy /Y "AutoRun_Add.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "AutoRun_Remove.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "Run_Headless.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "AutoClicker.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "SetupAutoClicker.py" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul

REM Batch files (NO Run_SetupRegions.bat)
echo     Copying launchers...
copy /Y "Run_Headless.bat" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "Run_TCGLiveMonitor_Command_Prompt.bat" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "Install_Dependencies.bat" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul

REM Configuration and assets (include pre-configured screen_regions.json)
echo     Copying configuration and assets...
copy /Y "requirements.txt" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "screen_regions.json" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "icon.ico" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "ding.mp3" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y ".gitignore" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul

REM Documentation
echo     Copying documentation...
copy /Y "README.md" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "RELEASE_NOTES_v2.1.md" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "QUICK_START_v2.0.md" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul
copy /Y "GITHUB_RELEASE_NOTES.md" "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0\" >nul

echo [OK] All files copied
echo.

REM Create ZIP package
echo [3/3] Creating ZIP package...
cd "Installers\Build"

REM Use PowerShell to create ZIP
powershell -Command "Compress-Archive -Path 'Pokemon-TCG-Live-Monitor-v2.1.0\*' -DestinationPath 'Pokemon-TCG-Live-Monitor-v2.1.0.zip' -Force"

if exist "Pokemon-TCG-Live-Monitor-v2.1.0.zip" (
    echo [OK] ZIP package created
) else (
    echo [ERROR] Failed to create ZIP
)

cd ..\..
echo.

REM Create installer info file
echo Creating INSTALLER_INFO.txt...
(
echo Pokemon TCG Live Monitor v2.1.0 - Release Package
echo ================================================================
echo.
echo This package contains:
echo   - Pokemon-TCG-Live-Monitor-v2.1.0.zip
echo.
echo INSTALLATION INSTRUCTIONS:
echo.
echo 1. Download Pokemon-TCG-Live-Monitor-v2.1.0.zip
echo 2. Extract to a permanent location (e.g., C:\TCGLiveMonitor)
echo 3. Open the extracted folder
echo 4. Go to the "Installers" folder (it will be at the top)
echo 5. Right-click "INSTALL_COMPLETE_v2.1.bat"
echo 6. Select "Run as Administrator"
echo 7. Follow the installation prompts
echo.
echo The installer will:
echo   - Check for Python 3.10+ (download if needed)
echo   - Auto-download and install Tesseract OCR
echo   - Install all Python dependencies
echo   - Prompt for OpenAI API key (optional)
echo   - Configure auto-start with Windows
echo.
echo SYSTEM REQUIREMENTS:
echo   - Windows 10 or 11
echo   - Internet connection (for initial setup)
echo   - 500 MB free disk space
echo.
echo SUPPORT:
echo   - Documentation: See README.md
echo   - Issues: https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/issues
echo.
echo Created: %date% %time%
) > "Installers\Build\INSTALLER_INFO.txt"

echo.
echo ================================================================
echo                 BUILD COMPLETE!
echo ================================================================
echo.
echo Release package created:
echo   Location: Installers\Build\
echo   File: Pokemon-TCG-Live-Monitor-v2.1.0.zip
echo   Size: 
for %%A in ("Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0.zip") do echo   %%~zA bytes
echo.
echo NEXT STEPS:
echo.
echo 1. Test the installer:
echo    - Extract the ZIP on a clean Windows machine
echo    - Run Installers\INSTALL_COMPLETE_v2.1.bat as Administrator
echo    - Verify all features work
echo.
echo 2. Upload to GitHub Release:
echo    - Go to: https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/releases
echo    - Edit the v2.1.0 release
echo    - Upload: Pokemon-TCG-Live-Monitor-v2.1.0.zip
echo    - Add installer instructions
echo.
echo 3. Update release notes:
echo    - Copy content from GITHUB_RELEASE_NOTES.md
echo    - Paste into GitHub release description
echo.
echo ================================================================
echo.
pause
