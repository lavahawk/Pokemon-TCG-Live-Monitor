@echo off
echo ================================================
echo TCG Live Monitor - Region Setup Tool
echo ================================================
echo.
echo This tool will help you define screen regions
echo for OCR detection (rank, username, etc.)
echo.
echo INSTRUCTIONS:
echo 1. Open Pokemon TCG Live to the main menu
echo 2. Make sure your rank is clearly visible
echo 3. Click "Take Screenshot" in the tool
echo 4. Click and drag to select the rank number area
echo 5. Click "Save Configuration"
echo.
pause

python SetupRegions.py

pause
