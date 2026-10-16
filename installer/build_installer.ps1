<#
  Builds the offline Windows installer for Pokemon TCG Live Monitor.

  Output: installer\Output\PokemonTCGLiveMonitor-<version>-Setup.exe

  The installer is fully self-contained: it carries its own Python 3.12
  runtime with every package pre-installed, plus Tesseract OCR. Nothing is
  downloaded or compiled on the user's PC, no admin rights are needed, and
  no system Python is touched - so it behaves the same on every Windows
  10/11 x64 machine.

  Steps
    1. Python runtime   official python.org NuGet build (relocatable, never
                        registered on the machine), pinned + SHA-256 checked;
                        requirements.txt installed (wheels preferred); unused
                        Qt modules / tests / dev files trimmed. Cached per
                        (Python version, requirements.txt hash).
    2. Tesseract OCR    tesseract.exe + DLLs + English data only.
    3. App files        exactly the files listed in release_manifest.txt.
    4. Smoke test       the staged runtime imports every module, renders a
                        Qt WebEngine page offscreen and OCRs a test image.
                        A broken bundle fails the build instead of shipping.
    5. Wizard artwork   generated from icon.ico.
    6. Inno Setup       compiles installer\PokemonTCGLiveMonitor.iss.

  Usage (from anywhere):
    powershell -NoProfile -ExecutionPolicy Bypass -File installer\build_installer.ps1 [-Clean] [-SkipSmokeTest]

  Needs on the BUILD machine only: internet (first run), Inno Setup 6, and a
  Tesseract install (the repo's tesseract\ folder, or C:\Program Files\Tesseract-OCR).
#>
param(
    [switch]$Clean,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root      = Split-Path -Parent $PSScriptRoot
$Build     = Join-Path $PSScriptRoot "build"
$Cache     = Join-Path $Build "cache"
$Stage     = Join-Path $Build "stage"
$OutDir    = Join-Path $PSScriptRoot "Output"

$PyVersion = "3.12.10"
$PySha256  = "0EB85C2DFCCCCF1B17352DE4C397F69194035B7D37149EACC16F1147D93DE3B8"
$PyUrl     = "https://www.nuget.org/api/v2/package/python/$PyVersion"

function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Info($msg) { Write-Host "    $msg" }
function Check-Exit($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)." } }
function Size-MB($path) {
    $sum = (Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    return [math]::Round($sum / 1MB)
}
function Remove-Paths($base, $patterns) {
    foreach ($p in $patterns) {
        Get-ChildItem -Path (Join-Path $base $p) -Force -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$Version = (Select-String -Path (Join-Path $Root "version.py") -Pattern 'APP_VERSION = "([\d.]+)"').Matches[0].Groups[1].Value
if (-not $Version) { throw "Could not read APP_VERSION from version.py" }
Write-Host "Pokemon TCG Live Monitor $Version - installer build" -ForegroundColor White

if ($Clean) { Remove-Item $Build -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $Cache, $OutDir | Out-Null
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

# ── 1. Python runtime ────────────────────────────────────────────────────
Step "Python $PyVersion runtime"
$reqHash = (Get-FileHash (Join-Path $Root "requirements.txt") -Algorithm SHA256).Hash.Substring(0, 12)
$RtCache = Join-Path $Build "runtime-$PyVersion-$reqHash"
if (Test-Path (Join-Path $RtCache ".complete")) {
    Info "Using cached runtime ($RtCache)"
} else {
    Remove-Item $RtCache -Recurse -Force -ErrorAction SilentlyContinue
    $zip = Join-Path $Cache "python-$PyVersion.zip"
    if (-not (Test-Path $zip)) {
        Info "Downloading $PyUrl"
        Invoke-WebRequest -Uri $PyUrl -OutFile "$zip.part" -UseBasicParsing
        Move-Item "$zip.part" $zip -Force
    }
    $hash = (Get-FileHash $zip -Algorithm SHA256).Hash
    if ($hash -ne $PySha256) { Remove-Item $zip -Force; throw "Python package checksum mismatch ($hash)." }
    $unz = Join-Path $Build "nupkg"
    Remove-Item $unz -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -Path $zip -DestinationPath $unz -Force
    Move-Item (Join-Path $unz "tools") $RtCache
    Remove-Item $unz -Recurse -Force

    $py = Join-Path $RtCache "python.exe"
    Info "Installing requirements..."
    & $py -m pip install --upgrade pip --disable-pip-version-check --no-warn-script-location -q
    Check-Exit "pip upgrade"
    # --prefer-binary: wheels wherever they exist; the few source-only pins
    # (e.g. pyperclip) are pure Python and build without a compiler.
    & $py -m pip install -r (Join-Path $Root "requirements.txt") --prefer-binary `
        --disable-pip-version-check --no-warn-script-location
    Check-Exit "pip install"

    Info "Trimming files the app never loads..."
    $before = Size-MB $RtCache
    $sp = Join-Path $RtCache "Lib\site-packages"
    $qt = Join-Path $sp "PySide6"
    # Build-time-only parts of the Python package itself.
    Remove-Paths $RtCache @("include", "libs", "Lib\test", "Lib\idlelib", "Lib\tkinter", "Lib\turtledemo", "Lib\ensurepip\_bundled")
    # Qt: dev tools, headers, QML and modules the app doesn't import
    # (app uses Core/Gui/Widgets/Test/WebEngineCore/WebEngineWidgets, plus
    # Network (card images), Pdf + PrintSupport (decklist printing); the
    # smoke test below proves the trimmed set still works).
    Remove-Paths $qt @("include", "typesystems", "glue", "metatypes", "scripts", "doc", "examples", "qml",
        "designer.exe", "linguist.exe", "assistant.exe", "lupdate.exe", "lrelease.exe", "qml*.exe",
        "balsam*.exe", "qsb.exe", "svgtoqml.exe", "uic.exe", "rcc.exe", "androiddeployqt*.exe", "*.pyi",
        "translations\qt*.qm")
    $unused = @("3D", "Quick3D", "Charts", "DataVisualization", "Graphs", "Multimedia", "SpatialAudio",
        "Designer", "UiTools", "Bluetooth", "Nfc", "Sensors", "SerialPort", "SerialBus",
        "TextToSpeech", "Location", "RemoteObjects", "Scxml", "StateMachine", "HttpServer",
        "VirtualKeyboard", "Help", "ShaderTools", "Quick3DPhysics", "Lottie", "WebView", "QuickTimeline")
    foreach ($m in $unused) {
        Remove-Paths $qt @("Qt6$m*.dll", "Qt$m*.pyd", "Qt$m*.pyi")
    }
    Remove-Paths $qt @("avcodec*.dll", "avformat*.dll", "avutil*.dll", "swresample*.dll", "swscale*.dll",
        "plugins\multimedia", "plugins\sceneparsers", "plugins\geometryloaders", "plugins\renderplugins",
        "plugins\assetimporters", "plugins\sensors", "plugins\canbus", "plugins\texttospeech",
        "plugins\designer", "plugins\qmltooling", "plugins\virtualkeyboard", "plugins\position\*serialnmea*")
    # Other packages: tests, docs, examples, video codecs OpenCV never uses here.
    Remove-Paths $sp @("pandas\tests", "numpy\*\tests", "numpy\tests", "matplotlib\tests", "pygame\examples",
        "pygame\docs", "pygame\tests", "cv2\opencv_videoio_ffmpeg*.dll", "setuptools", "_distutils_hack",
        "distutils-precedence.pth", "pip\_vendor\distlib\*.exe")
    Get-ChildItem $RtCache -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Info ("Runtime: {0} MB -> {1} MB" -f $before, (Size-MB $RtCache))
    New-Item -ItemType File -Path (Join-Path $RtCache ".complete") | Out-Null
}
Copy-Item $RtCache (Join-Path $Stage "runtime") -Recurse
Remove-Item (Join-Path $Stage "runtime\.complete") -Force

# ── 2. Tesseract OCR ─────────────────────────────────────────────────────
Step "Tesseract OCR"
$tessSrc = @((Join-Path $Root "tesseract"), "C:\Program Files\Tesseract-OCR", "${env:ProgramFiles(x86)}\Tesseract-OCR") |
    Where-Object { Test-Path (Join-Path $_ "tesseract.exe") } | Select-Object -First 1
if (-not $tessSrc) {
    throw "Tesseract not found on the build machine. Install it (https://github.com/UB-Mannheim/tesseract/wiki) or copy it into the repo's tesseract\ folder."
}
$tessDst = Join-Path $Stage "tesseract"
New-Item -ItemType Directory -Force -Path (Join-Path $tessDst "tessdata") | Out-Null
Copy-Item (Join-Path $tessSrc "tesseract.exe") $tessDst
# The 26 DLLs tesseract.exe 5.4 actually loads (found by removing each DLL and
# re-running OCR on PNG/JPG/BMP). The other 25 belong to the training tools.
# A different Tesseract version may need others: then everything is copied
# and the smoke test still verifies OCR works.
$tessDlls = @("libLerc.dll", "libarchive-13.dll", "libb2-1.dll", "libbz2-1.dll", "libcrypto-3-x64.dll",
    "libdeflate.dll", "libexpat-1.dll", "libgcc_s_seh-1.dll", "libgif-7.dll", "libiconv-2.dll", "libjbig-0.dll",
    "libjpeg-8.dll", "libleptonica-6.dll", "liblz4.dll", "liblzma-5.dll", "libopenjp2-7.dll", "libpng16-16.dll",
    "libsharpyuv-0.dll", "libstdc++-6.dll", "libtesseract-5.dll", "libtiff-6.dll", "libwebp-7.dll",
    "libwebpmux-3.dll", "libwinpthread-1.dll", "libzstd.dll", "zlib1.dll")
if (@($tessDlls | Where-Object { -not (Test-Path (Join-Path $tessSrc $_)) }).Count -eq 0) {
    foreach ($d in $tessDlls) { Copy-Item (Join-Path $tessSrc $d) $tessDst }
} else {
    Write-Warning "Unfamiliar Tesseract build - copying all of its DLLs."
    Copy-Item (Join-Path $tessSrc "*.dll") $tessDst
}
Copy-Item (Join-Path $tessSrc "tessdata\eng.traineddata") (Join-Path $tessDst "tessdata")
foreach ($d in "configs", "tessconfigs") {
    $p = Join-Path $tessSrc "tessdata\$d"
    if (Test-Path $p) { Copy-Item $p (Join-Path $tessDst "tessdata") -Recurse }
}
Info ("From {0} ({1} MB)" -f $tessSrc, (Size-MB $tessDst))

# ── 3. App files ─────────────────────────────────────────────────────────
Step "Application files (release_manifest.txt)"
$count = 0
foreach ($line in Get-Content (Join-Path $Root "release_manifest.txt")) {
    $entry = $line.Trim()
    if (-not $entry -or $entry.StartsWith("#")) { continue }
    $optional = $entry.EndsWith("?")
    $rel = $entry.TrimEnd("?")
    $src = Join-Path $Root $rel
    if (-not (Test-Path $src)) {
        if ($optional) { continue }
        throw "Manifest file missing: $rel"
    }
    $dst = Join-Path $Stage $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
    Copy-Item $src $dst
    $count++
}
Info "$count files"

# ── 4. Smoke test ────────────────────────────────────────────────────────
if ($SkipSmokeTest) {
    Write-Warning "Smoke test skipped."
} else {
    Step "Smoke test of the staged bundle"
    & (Join-Path $Stage "runtime\python.exe") -I (Join-Path $PSScriptRoot "smoke_test.py") $Stage
    Check-Exit "Smoke test"
}
# Bytecode written by the smoke test is per-machine cache; don't ship it.
Get-ChildItem $Stage -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ── 5. Wizard artwork ────────────────────────────────────────────────────
Step "Wizard artwork"
$art = Join-Path $Build "art"
New-Item -ItemType Directory -Force -Path $art | Out-Null
& (Join-Path $Stage "runtime\python.exe") -I (Join-Path $PSScriptRoot "make_wizard_art.py") (Join-Path $Root "icon.ico") $art
Check-Exit "Wizard artwork"

# ── 6. Compile installer ─────────────────────────────────────────────────
Step "Inno Setup"
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php" }
Info ("Staged bundle: {0} MB" -f (Size-MB $Stage))
& $iscc "/DAppVersion=$Version" "/DStageDir=$Stage" "/DArtDir=$art" "/DRootDir=$Root" "/O$OutDir" `
    (Join-Path $PSScriptRoot "PokemonTCGLiveMonitor.iss")
Check-Exit "Inno Setup compile"

$exe = Join-Path $OutDir "PokemonTCGLiveMonitor-$Version-Setup.exe"
$sha = (Get-FileHash $exe -Algorithm SHA256).Hash
Set-Content -Path "$exe.sha256" -Value "$sha  $(Split-Path $exe -Leaf)" -Encoding ASCII
Write-Host ""
Write-Host ("Built {0} ({1:N0} MB)" -f $exe, ((Get-Item $exe).Length / 1MB)) -ForegroundColor Green
Write-Host "SHA-256 $sha"
