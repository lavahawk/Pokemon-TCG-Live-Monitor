<#
  Pokemon TCG Live Monitor - one-shot setup bootstrap (v2.4)

  Used by every installer (Inno Setup, INSTALL_COMPLETE bat, manual runs):
    1. Find a compatible Python (3.10 - 3.12). The pinned packages (numpy 1.26,
       pandas 2.2, pygame 2.5, ...) have no wheels for Python 3.13+, so a
       newer default Python makes pip fail.
    2. If none is found, download the official python.org 3.12 installer and
       install it for the current user only (no admin needed).
    3. Run setup_install.py with it (venv, dependencies, Tesseract, auto-start,
       launch).

  Usage:
    powershell -NoProfile -ExecutionPolicy Bypass -File bootstrap_setup.ps1 [-AutoStart | -NoAutoStart] [-Launch] [-NoPause]
#>
param(
    [switch]$AutoStart,
    [switch]$NoAutoStart,
    [switch]$Launch,
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonVersion = "3.12.10"
$PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
$LogFile = Join-Path $AppDir "Logs\setup.log"
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "Logs") | Out-Null

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Test-Python($exe) {
    if (-not $exe -or -not (Test-Path $exe)) { return $false }
    try {
        $v = & $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if (-not $v) { return $false }
        $parts = $v.Trim().Split(".")
        return ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10 -and [int]$parts[1] -le 12)
    } catch { return $false }
}

function Find-Python {
    # 1) The Python launcher (py.exe), newest compatible first.
    foreach ($ver in @("3.12", "3.11", "3.10")) {
        try {
            $exe = & py "-$ver" -c "import sys; print(sys.executable)" 2>$null
            if ($exe -and (Test-Python $exe.Trim())) { return $exe.Trim() }
        } catch { }
    }
    # 2) Registry (per-user and machine installs).
    foreach ($root in @("HKCU:\Software\Python\PythonCore", "HKLM:\Software\Python\PythonCore", "HKLM:\Software\WOW6432Node\Python\PythonCore")) {
        foreach ($ver in @("3.12", "3.11", "3.10")) {
            try {
                $path = (Get-ItemProperty -Path "$root\$ver\InstallPath" -ErrorAction Stop)."(default)"
                if ($path) {
                    $exe = Join-Path $path "python.exe"
                    if (Test-Python $exe) { return $exe }
                }
            } catch { }
        }
    }
    # 3) Default per-user install locations.
    foreach ($ver in @("312", "311", "310")) {
        $exe = Join-Path $env:LOCALAPPDATA "Programs\Python\Python$ver\python.exe"
        if (Test-Python $exe) { return $exe }
    }
    # 4) Whatever "python" is on PATH (if it happens to be compatible).
    try {
        $exe = (Get-Command python -ErrorAction Stop).Source
        if (Test-Python $exe) { return $exe }
    } catch { }
    return $null
}

function Install-Python {
    $installer = Join-Path ([System.IO.Path]::GetTempPath()) ("python-setup-" + [guid]::NewGuid().ToString() + ".exe")
    Log "Downloading Python $PythonVersion from python.org ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -Uri $PythonUrl -OutFile $installer -UseBasicParsing
    $sig = Get-AuthenticodeSignature $installer
    if ($sig.Status -ne "Valid" -or $sig.SignerCertificate.Subject -notmatch "Python Software Foundation") {
        Remove-Item $installer -Force -ErrorAction SilentlyContinue
        throw "Downloaded Python installer failed its signature check ($($sig.Status))."
    }
    Log "Installing Python $PythonVersion for the current user (no admin) ..."
    $p = Start-Process -FilePath $installer -ArgumentList "/quiet", "InstallAllUsers=0", "Include_launcher=1", "InstallLauncherAllUsers=0", "PrependPath=0", "Include_test=0" -Wait -PassThru
    Remove-Item $installer -Force -ErrorAction SilentlyContinue
    if ($p.ExitCode -ne 0) { throw "Python installer exited with code $($p.ExitCode)." }
}

try {
    Log "=== Pokemon TCG Live Monitor setup ==="
    Log "App folder: $AppDir"
    $python = Find-Python
    if (-not $python) {
        Log "No compatible Python (3.10-3.12) found."
        Install-Python
        $python = Find-Python
    }
    if (-not $python) { throw "Python 3.12 could not be installed. Install it from https://www.python.org/downloads/ and run this setup again." }
    Log "Using Python: $python"

    $setupArgs = @((Join-Path $AppDir "setup_install.py"))
    if ($AutoStart) { $setupArgs += "--autostart" } elseif ($NoAutoStart) { $setupArgs += "--no-autostart" }
    if ($Launch) { $setupArgs += "--launch" }
    & $python @setupArgs
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "setup_install.py reported a problem (exit code $code). See Logs\setup.log." }
    Log "Setup finished successfully."
} catch {
    Log "SETUP FAILED: $($_.Exception.Message)"
    Read-Host "Setup failed - press Enter to close" | Out-Null
    exit 1
}
if (-not $NoPause) { Start-Sleep -Seconds 3 }
exit 0
