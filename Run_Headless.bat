@echo off
REM Launch TCG Live Monitor in Headless Mode (No Console)
echo Starting TCG Live Monitor (Headless Mode)...
python Run_Headless.py
timeout /t 3
