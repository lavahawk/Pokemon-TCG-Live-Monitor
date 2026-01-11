@echo off
title Test Tesseract Auto-Download

echo Testing Tesseract OCR auto-download...
echo.

set "TEST_INSTALLER=%TEMP%\test-tesseract-ocr-setup.exe"

echo Step 1: Downloading Tesseract OCR installer...
echo URL: https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe
echo.

powershell -Command "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe' -OutFile $env:TEMP'\test-tesseract-ocr-setup.exe' -UseBasicParsing"

echo.
echo Step 2: Checking if file downloaded...

if exist "%TEST_INSTALLER%" (
    echo [SUCCESS] File downloaded!
    for %%A in ("%TEST_INSTALLER%") do echo File size: %%~zA bytes
    
    echo.
    echo Cleaning up test file...
    del "%TEST_INSTALLER%" >nul 2>&1
    echo [OK] Test complete!
) else (
    echo [ERROR] Download failed - file not found
    echo.
    echo Please check:
    echo   1. Internet connection
    echo   2. Firewall settings
    echo   3. GitHub accessibility
)

echo.
pause
