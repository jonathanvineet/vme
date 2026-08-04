# Just creates a venv (if needed) and installs requirements.txt using
# whatever Python is on PATH. No winget, no CMake/Build Tools checks,
# no auto-install of anything - assumes you already installed Python
# (and, if dlib fails to build, CMake + VS Build Tools with the
# "Desktop development with C++" workload) yourself.
#
# Usage:  .\install_requirements.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Log($msg)  { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Fail "python is not on PATH. Install Python and make sure 'Add python.exe to PATH' was checked, then open a NEW terminal and re-run this script."
}

Log "Using python: $(python --version) ($((Get-Command python).Source))"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if ((Test-Path ".venv") -and -not (Test-Path $venvPython)) {
    Log "Found an incomplete .venv - removing it"
    Remove-Item -Recurse -Force ".venv"
}

if (-not (Test-Path ".venv")) {
    Log "Creating virtual environment (.venv)"
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "python -m venv failed - your Python install may be missing the venv module or its launcher files" }
} else {
    Log "Virtual environment already exists"
}

if (-not (Test-Path $venvPython)) {
    Fail "venv creation reported success but $venvPython is still missing."
}

$venvPip = Join-Path $PSScriptRoot ".venv\Scripts\pip.exe"

Log "Upgrading pip/setuptools/wheel"
& $venvPython -m pip install --upgrade pip setuptools wheel

Log "Installing packages from requirements.txt (dlib compiles from source; can take 5-15 min - if it fails, install CMake and Visual Studio Build Tools' 'Desktop development with C++' workload, then re-run this script)"
& $venvPip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "pip install -r requirements.txt failed - see the error above" }

Log "Done. Activate with: .venv\Scripts\Activate.ps1"
Log "Then start everything with: .\start_all.ps1"
