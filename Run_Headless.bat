@echo off
setlocal
cd /d "%~dp0"

if /I not "%~1"=="__hidden__" (
    powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -WindowStyle Hidden -FilePath $env:ComSpec -ArgumentList '/c','""%~f0"" __hidden__' | Out-Null"
    exit /b
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" /b ".venv\Scripts\pythonw.exe" "Run_Headless.py"
    exit /b 0
)

powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Could not find .venv\\Scripts\\pythonw.exe. Please run the installer first.','Pokemon TCG Live Monitor') | Out-Null"
exit /b 1
