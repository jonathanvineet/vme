# Sets up the face-recognition attendance system on Windows, without WSL.
# Install Python 3.11+ yourself first (python.org, check "Add python.exe to
# PATH"); this script installs CMake + VS Build Tools (needed to compile
# dlib) if missing, then creates .venv and installs requirements.txt.
#
# Usage (from PowerShell, in the facerecog folder):
#   .\setup.ps1
#
# If PowerShell blocks the script with an "execution policy" error, run once:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#
# Safe to re-run - every step checks whether it's already done.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Log($msg)  { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Fail "winget (Windows Package Manager) is not available. It ships with Windows 10 21H2+/Windows 11. Update Windows, or install App Installer from the Microsoft Store, then re-run this script."
}

# 1. Python
# This script does NOT install Python - install it yourself first (from
# python.org, checking "Add python.exe to PATH"), then run this script.
# It still validates what's on PATH before trusting it, since some machines
# have a "python" that isn't a real, complete CPython install (e.g. a
# stripped interpreter bundled with unrelated hardware/software). The only
# reliable test is to actually try building a venv with it.
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Fail "python is not on PATH. Install Python 3.11+ from python.org (check 'Add python.exe to PATH' during install), open a NEW PowerShell window, and re-run .\setup.ps1"
}
$pythonExe = (Get-Command python).Source
$probeDir = Join-Path $env:TEMP "vme_venv_probe_$([guid]::NewGuid().ToString('N'))"
& $pythonExe -m venv $probeDir *> $null
$venvWorks = ($LASTEXITCODE -eq 0) -and (Test-Path (Join-Path $probeDir "Scripts\python.exe"))
Remove-Item -Recurse -Force $probeDir -ErrorAction SilentlyContinue
if (-not $venvWorks) {
    Fail "The 'python' on PATH ($pythonExe) can't create a working venv - it's not a complete Python install (possibly bundled by other software). Install Python 3.11+ from python.org, make sure it comes first on PATH, open a NEW PowerShell window, and re-run .\setup.ps1"
}
Log "Using Python: $pythonExe ($(& $pythonExe --version))"

# 2. CMake (required to build dlib from source)
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    Log "Installing CMake via winget"
    winget install -e --id Kitware.CMake --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { Fail "winget install CMake failed (exit $LASTEXITCODE) - see the error above" }
    Log "CMake installed. Close this terminal, open a NEW PowerShell window, and re-run .\setup.ps1"
    exit 0
} else {
    Log "CMake already installed"
}

# 3. Visual Studio C++ Build Tools (required to compile dlib on Windows)
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$hasBuildTools = $false
if (Test-Path $vswhere) {
    $found = & $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($found) { $hasBuildTools = $true }
}
if (-not $hasBuildTools) {
    Log "Installing Visual Studio Build Tools (C++ workload) via winget - this is the biggest download, can take a while"
    winget install -e --id Microsoft.VisualStudio.2022.BuildTools --source winget --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { Fail "winget install Build Tools failed (exit $LASTEXITCODE) - see the error above" }
    Log "Build Tools installed. Close this terminal, open a NEW PowerShell window, and re-run .\setup.ps1"
    exit 0
} else {
    Log "Visual Studio C++ Build Tools already installed"
}

# 4. Virtual environment
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$venvPip    = Join-Path $PSScriptRoot ".venv\Scripts\pip.exe"

if ((Test-Path ".venv") -and -not (Test-Path $venvPython)) {
    Log "Found an incomplete .venv from a previous failed run - removing it"
    Remove-Item -Recurse -Force ".venv"
}

if (-not (Test-Path ".venv")) {
    Log "Creating virtual environment (.venv)"
    & $pythonExe -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "python -m venv failed" }
} else {
    Log "Virtual environment already exists"
}

if (-not (Test-Path $venvPython)) {
    Fail "venv creation reported success but $venvPython is still missing - something is wrong with the Python install at $pythonExe"
}

Log "Upgrading pip/setuptools/wheel"
& $venvPython -m pip install --upgrade pip setuptools wheel | Out-Null

# 5. Project dependencies (dlib compiles from source here - can take 5-15 min)
Log "Installing Python packages from requirements.txt (dlib compiles from source; this can take a while, please be patient)"
& $venvPip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "pip install -r requirements.txt failed - see the error above" }

Log "Done. Activate the environment in future shells with: .venv\Scripts\Activate.ps1"
Log "Then start everything with: .\start_all.ps1"
