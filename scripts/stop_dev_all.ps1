# Stop API (8000/8010) and common dev frontend ports (5173, 5000).
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Stop-PortListeners([int]$port) {
    $pids = @()
    $pattern = ":$port\s"
    netstat -ano | Select-String $pattern | ForEach-Object {
        $line = $_.Line.Trim()
        if ($line -match "LISTENING\s+(\d+)\s*$") {
            $pids += [int]$Matches[1]
        }
    }
    $pids = @($pids | Sort-Object -Unique)
    if ($pids.Count -eq 0) {
        Write-Host "Port $port is free."
        return
    }
    Write-Host "Stopping port ${port}: $($pids -join ', ')"
    foreach ($procId in $pids) {
        taskkill /F /T /PID $procId 2>$null | Out-Null
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Stopping Swigar API ..." -ForegroundColor Gray
& (Join-Path $Root "scripts\stop_api.ps1")

Write-Host "Stopping dev frontends ..." -ForegroundColor Gray
Stop-PortListeners 5173
Stop-PortListeners 5000

Write-Host "Done." -ForegroundColor Green
