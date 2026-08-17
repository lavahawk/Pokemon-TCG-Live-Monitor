@echo off
echo ================================================
echo Pokemon TCG Live Monitor - Setup Script
echo ================================================
echo.
echo This will install all required Python packages
echo including NEW OCR dependencies for rank detection
echo.
pause

echo.
echo Installing Python packages...
pip install -r requirements.txt

echo.
echo ================================================
echo Installation complete!
echo ================================================
echo.
echo IMPORTANT: You also need to install Tesseract OCR
echo.
echo Download from: https://github.com/UB-Mannheim/tesseract/wiki
echo Install to: C:\Program Files\Tesseract-OCR
echo.
echo After installing Tesseract, you can run the monitor:
echo   - Run_TCGLiveMonitor_Command_Prompt.bat  (with console)
echo   - Run_Headless.bat                       (background)
echo.
echo NOTE: Screen regions are pre-configured for standard
echo 1920x1080 displays and auto-adjust to your resolution.
echo.
pause
