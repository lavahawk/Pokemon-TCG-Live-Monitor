@echo off
title Pokemon TCG Live Monitor - Complete System
color 0B
cls

echo.
echo ================================================
echo    POKEMON TCG LIVE MONITOR - LAUNCHER
echo ================================================
echo.
echo This will start the complete monitoring system:
echo.
echo  1. Battle Log Monitor (clipboard watcher)
echo  2. Modern Overlay UI (auto-starts with monitor)
echo  3. AI Battle Analysis
echo  4. OCR Rank/Deck Detection
echo  5. League Pokeball Icons
echo.
echo The overlay will:
echo  - Show current Elo with league icon
echo  - Display max Elo achieved
echo  - Track today's win/loss record
echo  - Follow game window automatically
echo  - Allow click-through (won't block gameplay)
echo.
echo ================================================
echo.
pause
cls

echo.
echo ================================================
echo    STARTING MONITORING SYSTEM...
echo ================================================
echo.
python TCGLiveMonitor.py

echo.
echo ================================================
echo    SHUTTING DOWN...
echo ================================================
echo.
pause
