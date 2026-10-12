@echo off
REM Developer setup: creates .venv and installs requirements for running from source.
REM End users should use the installer (installer\build_installer.ps1 builds it).
setlocal
cd /d "%~dp0"
set "PY="
for %%V in (3.12 3.11 3.10) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    echo Python 3.10-3.12 not found. Install Python 3.12 from https://www.python.org/downloads/
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo Creating .venv with %PY% ...
    %PY% -m venv .venv || goto :fail
)
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check -q || goto :fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check || goto :fail
echo.
echo Done. Run Run_TCGLiveMonitor_Command_Prompt.bat to start the monitor.
echo (OCR needs Tesseract: install it, or copy a tesseract\ folder next to the code.)
pause
exit /b 0
:fail
echo.
echo Setup failed - see the messages above.
pause
exit /b 1
