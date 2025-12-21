@echo off
color 0C
title Remove Auto-Start v2.0

echo ============================================================
echo    Remove Pokemon TCG Live Monitor v2.0 from Auto-Start
echo ============================================================
echo.

REM Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This requires Administrator privileges!
    echo Please right-click and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)

echo Removing scheduled task...
schtasks /delete /tn "PokemonTCGLiveMonitor_v2" /f

if %errorLevel% equ 0 (
    echo [OK] Auto-start removed successfully
) else (
    echo [!] Task not found or already removed
)

echo.
echo Done! The monitor will no longer start automatically.
echo You can still run it manually with Start_GUI_Mode_v2.0.bat
echo.
pause
