# Bootstrap a brand-new Windows machine (no Python, nothing) so it can run
# the face-recognition attendance system, without needing WSL.
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
# Some machines already have a "python" on PATH that isn't a real, complete
# CPython install (e.g. a stripped interpreter bundled with unrelated
# hardware/software, missing the venv/ensurepip modules). Get-Command alone
# can't tell the difference, so actually probe it before trusting it.
function Test-PythonOk($exe) {
    if (-not $exe -or -not (Test-Path $exe)) { return $false }
    & $exe -c "import venv, ensurepip" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Find-Python311 {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $viaLauncher = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-PythonOk $viaLauncher)) { return $viaLauncher }
    }
    $standard = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-PythonOk $standard) { return $standard }
    $onPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (Test-PythonOk $onPath) { return $onPath }
    return $null
}

$pythonExe = Find-Python311
if (-not $pythonExe) {
    Log "No working Python 3.11 install found (existing 'python' on PATH may be incomplete/broken) - installing a fresh copy via winget"
    winget install -e --id Python.Python.3.11 --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { Fail "winget install Python failed (exit $LASTEXITCODE) - see the error above" }
    $pythonExe = Find-Python311
    if (-not $pythonExe) { Fail "Python was installed but could not be located automatically. Close this terminal, open a NEW PowerShell window, and re-run .\setup.ps1" }
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
if (-not (Test-Path ".venv")) {
    Log "Creating virtual environment (.venv)"
    & $pythonExe -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "python -m venv failed" }
} else {
    Log "Virtual environment already exists"
}

$venvPython = ".venv\Scripts\python.exe"
$venvPip    = ".venv\Scripts\pip.exe"

Log "Upgrading pip/setuptools/wheel"
& $venvPython -m pip install --upgrade pip setuptools wheel | Out-Null

# 5. Project dependencies (dlib compiles from source here - can take 5-15 min)
Log "Installing Python packages from requirements.txt (dlib compiles from source; this can take a while, please be patient)"
& $venvPip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "pip install -r requirements.txt failed - see the error above" }

Log "Done. Activate the environment in future shells with: .venv\Scripts\Activate.ps1"
Log "Then start everything with: .\start_all.ps1"
