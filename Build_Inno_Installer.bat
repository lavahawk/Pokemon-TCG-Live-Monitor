@echo off
setlocal
title Build Inno Setup Installer - Pokemon TCG Live Monitor v2.3.0

echo ================================================================
echo     Pokemon TCG Live Monitor v2.3.0
echo          Inno Setup Installer Builder
echo ================================================================
echo.

REM 1. Build the release ZIP package
echo [1/3] Building release ZIP package...
call Build_Release_Package.bat
echo.

REM 2. Locate Inno Setup compiler
echo [2/3] Locating Inno Setup compiler (ISCC.exe)...
set "ISCC="
for %%P in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) do (
    if exist %%P set "ISCC=%%~P"
)

if not defined ISCC (
    echo.
    echo [ERROR] Inno Setup 6 was not found.
    echo Please install it from: https://jrsoftware.org/isinfo.php
    echo.
    pause
    exit /b 1
)
echo       [OK] Found: %ISCC%
echo.

REM 3. Compile the installer
echo [3/3] Compiling Inno Setup installer...
"%ISCC%" "installer_setup.iss"
if %errorLevel% neq 0 (
    echo.
    echo [ERROR] Installer compilation failed.
    echo.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo                 BUILD COMPLETE!
echo ================================================================
echo.
echo Installer created:
echo   Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0-Setup.exe
echo.
echo Upload to GitHub Release:
echo   - Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0.zip
echo   - Installers\Build\Pokemon-TCG-Live-Monitor-v2.3.0-Setup.exe
echo.
echo ================================================================
echo.
pause