@echo off
title Pokemon TCG Live Monitor v2.1 - Remove Auto-Start

echo ================================================================
echo        Pokemon TCG Live Monitor v2.1
echo              Remove from Windows Startup
echo ================================================================
echo.

REM Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Administrator privileges required!
    echo.
    echo Please right-click this file and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)

echo Removing scheduled task...
echo.

REM Delete both v2.0 and v2.1 tasks
schtasks /delete /tn "PokemonTCGLiveMonitor_v2" /f >nul 2>&1
schtasks /delete /tn "PokemonTCGLiveMonitor_v2.1" /f >nul 2>&1

if %errorLevel% neq 0 (
    echo [WARNING] No scheduled task found to remove
    echo The monitor may not have been configured for auto-start
) else (
    echo [OK] Auto-start removed successfully
    echo The monitor will no longer start automatically on login
)

echo.
echo To add back to startup, run:
echo   python AutoRun_Add.py
echo.
pause
