# Uninstalls the Python that setup.ps1 installed via winget, and clears out
# the .venv that was built against it, so you can install Python manually
# and start clean.
#
# Usage:  .\uninstall_python.ps1

Set-Location -Path $PSScriptRoot

function Log($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

if (Get-Command winget -ErrorAction SilentlyContinue) {
    $installed = winget list --id Python.Python.3.11 --source winget 2>$null
    if ($LASTEXITCODE -eq 0 -and $installed -match "Python.Python.3.11") {
        Log "Uninstalling Python.Python.3.11 via winget"
        winget uninstall -e --id Python.Python.3.11 --source winget
        if ($LASTEXITCODE -ne 0) {
            Write-Host "winget uninstall reported an error (exit $LASTEXITCODE) - it may already be gone, or need Add/Remove Programs instead." -ForegroundColor Yellow
        }
    } else {
        Log "No winget-tracked Python.Python.3.11 install found - nothing to uninstall via winget"
    }
} else {
    Write-Host "winget not found - if Python was installed manually, remove it via Settings > Apps." -ForegroundColor Yellow
}

$standardInstall = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311"
if (Test-Path $standardInstall) {
    Log "Removing leftover install folder: $standardInstall"
    Remove-Item -Recurse -Force $standardInstall
}

if (Test-Path ".venv") {
    Log "Removing .venv (was built against the uninstalled Python)"
    Remove-Item -Recurse -Force ".venv"
}

Log "Done. Install your own Python 3.11+ (from python.org, make sure to check 'Add python.exe to PATH'), then run .\setup.ps1 again - it will pick up your install and just handle CMake/Build Tools/venv/pip."
