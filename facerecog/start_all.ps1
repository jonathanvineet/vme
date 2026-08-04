# Starts the in-gate, out-gate, and admin servers together (native Windows).
# Ctrl+C stops all three. Logs go to logs\*.log.
#
# Usage:  .\start_all.ps1

Set-Location -Path $PSScriptRoot
New-Item -ItemType Directory -Force -Path logs | Out-Null

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "No .venv found - run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

$env:GOOGLE_SHEET_ID = "1CzBMtY1gtp0nB1j_0tZvGuLuEkH_Po4mgl8mfF9rVGo"
$env:GOOGLE_SERVICE_ACCOUNT_FILE = (Join-Path (Get-Location) "secrets\google-service-account.json")

$PORT_IN = 5050
$PORT_OUT = 5051
$PORT_ADMIN = 5052

foreach ($port in @($PORT_IN, $PORT_OUT, $PORT_ADMIN)) {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Write-Host "Port $port is in use by PID $($c.OwningProcess), killing it..."
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

$procs = @()
$procs += Start-Process -FilePath $venvPython -ArgumentList "-u gate_server.py --mode in --port $PORT_IN" `
    -RedirectStandardOutput "logs\gate_in.log" -RedirectStandardError "logs\gate_in.err.log" -NoNewWindow -PassThru
$procs += Start-Process -FilePath $venvPython -ArgumentList "-u gate_server.py --mode out --port $PORT_OUT" `
    -RedirectStandardOutput "logs\gate_out.log" -RedirectStandardError "logs\gate_out.err.log" -NoNewWindow -PassThru
$procs += Start-Process -FilePath $venvPython -ArgumentList "-u admin_server.py --port $PORT_ADMIN" `
    -RedirectStandardOutput "logs\admin.log" -RedirectStandardError "logs\admin.err.log" -NoNewWindow -PassThru

$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch "Loopback" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
if (-not $ip) { $ip = "<your-ip>" }

Start-Sleep -Seconds 3
Write-Host ""
Write-Host "All servers running:"
Write-Host "  IN gate:    https://${ip}:$PORT_IN"
Write-Host "  OUT gate:   https://${ip}:$PORT_OUT"
Write-Host "  Admin:      https://${ip}:$PORT_ADMIN/login"
Write-Host ""
Write-Host "Logs: logs\gate_in.log logs\gate_out.log logs\admin.log"
Write-Host "Press Ctrl+C to stop everything."

try {
    Wait-Process -Id ($procs | ForEach-Object { $_.Id })
} finally {
    Write-Host "`nStopping all servers..."
    foreach ($p in $procs) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
}
