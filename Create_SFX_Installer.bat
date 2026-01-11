@echo off
setlocal enabledelayedexpansion
title Create Self-Extracting Installer for Pokemon TCG Live Monitor v2.1.0

echo ================================================================
echo     Pokemon TCG Live Monitor v2.1.0
echo         Self-Extracting Installer Creator
echo ================================================================
echo.

REM First, build the release package
echo [1/4] Building release package...
call Build_Release_Package.bat
if %errorLevel% neq 0 (
    echo [ERROR] Failed to build release package
    pause
    exit /b 1
)
echo.

REM Check if 7-Zip is installed
echo [2/4] Checking for 7-Zip...
set "SEVENZIP="
if exist "C:\Program Files\7-Zip\7z.exe" set "SEVENZIP=C:\Program Files\7-Zip\7z.exe"
if exist "C:\Program Files (x86)\7-Zip\7z.exe" set "SEVENZIP=C:\Program Files (x86)\7-Zip\7z.exe"

if "!SEVENZIP!"=="" (
    echo [!] 7-Zip not found
    echo.
    echo Downloading 7-Zip installer...
    
    REM Download 7-Zip installer
    powershell -Command "Invoke-WebRequest -Uri 'https://www.7-zip.org/a/7z2301-x64.exe' -OutFile '%TEMP%\7zip-installer.exe' -UseBasicParsing"
    
    if exist "%TEMP%\7zip-installer.exe" (
        echo Installing 7-Zip...
        start /wait "" "%TEMP%\7zip-installer.exe" /S
        del "%TEMP%\7zip-installer.exe" >nul 2>&1
        
        REM Check again
        if exist "C:\Program Files\7-Zip\7z.exe" (
            set "SEVENZIP=C:\Program Files\7-Zip\7z.exe"
            echo [OK] 7-Zip installed
        ) else (
            echo [ERROR] 7-Zip installation failed
            pause
            exit /b 1
        )
    ) else (
        echo [ERROR] Failed to download 7-Zip
        pause
        exit /b 1
    )
) else (
    echo [OK] 7-Zip found
)
echo.

REM Extract the ZIP and prepare for SFX
echo [3/4] Preparing SFX package...
cd Installers\Build

REM Create SFX config file
echo ;!@Install@!UTF-8! > config.txt
echo Title="Pokemon TCG Live Monitor v2.1.0 - Installation" >> config.txt
echo BeginPrompt="This will install Pokemon TCG Live Monitor v2.1.0\n\nClick Install to continue" >> config.txt
echo Progress="yes" >> config.txt
echo RunProgram="Installers\INSTALL_COMPLETE_v2.1.bat" >> config.txt
echo Directory="%%ProgramFiles%%\PokemonTCGLiveMonitor" >> config.txt
echo GUIMode="2" >> config.txt
echo ;!@InstallEnd@! >> config.txt

REM Create the SFX archive
echo Creating self-extracting installer...
"!SEVENZIP!" a -t7z "temp_archive.7z" "Pokemon-TCG-Live-Monitor-v2.1.0\*" -mx9 >nul

REM Get 7-Zip SFX module
if exist "C:\Program Files\7-Zip\7z.sfx" (
    copy /b "C:\Program Files\7-Zip\7z.sfx" + config.txt + temp_archive.7z "Pokemon-TCG-Live-Monitor-v2.1.0-Installer.exe" >nul
) else if exist "C:\Program Files (x86)\7-Zip\7z.sfx" (
    copy /b "C:\Program Files (x86)\7-Zip\7z.sfx" + config.txt + temp_archive.7z "Pokemon-TCG-Live-Monitor-v2.1.0-Installer.exe" >nul
) else (
    echo [ERROR] 7-Zip SFX module not found
    pause
    exit /b 1
)

REM Clean up
del config.txt >nul 2>&1
del temp_archive.7z >nul 2>&1

cd ..\..

if exist "Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0-Installer.exe" (
    echo [OK] Self-extracting installer created
) else (
    echo [ERROR] Failed to create SFX installer
    pause
    exit /b 1
)

echo.
echo [4/4] Finalizing...
echo.
echo ================================================================
echo                 BUILD COMPLETE!
echo ================================================================
echo.
echo Self-extracting installer created:
echo   Location: Installers\Build\
echo   File: Pokemon-TCG-Live-Monitor-v2.1.0-Installer.exe
echo   Size: 
for %%A in ("Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0-Installer.exe") do echo   %%~zA bytes (%%~zAK KB)
echo.
echo FEATURES:
echo   [+] Single portable EXE file
echo   [+] Auto-extracts to Program Files
echo   [+] Runs installer automatically
echo   [+] Professional installation wizard
echo   [+] No manual extraction needed
echo.
echo HOW TO USE:
echo   1. Share the .exe file
echo   2. User double-clicks it
echo   3. Clicks "Install"
echo   4. Application auto-installs
echo.
echo NEXT STEPS:
echo   1. Test: Installers\Build\Pokemon-TCG-Live-Monitor-v2.1.0-Installer.exe
echo   2. Upload to GitHub Release
echo   3. Share with users!
echo.
echo ================================================================
echo.
pause
