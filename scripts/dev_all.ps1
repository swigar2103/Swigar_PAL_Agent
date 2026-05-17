# Start Swigar API + debug-dashboard + TacticalDuel in separate terminals.
# Usage: .\scripts\dev_all.ps1
param(
    [switch]$SkipStopApi,
    [int]$HealthWaitSec = 90
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Missing .venv. Run: python -m venv .venv; .\.venv\Scripts\pip install -e . -e ./mempalace-reference"
    exit 1
}

function Test-PortListening([int]$Port) {
    $pattern = ":$Port\s"
    return [bool](
        netstat -ano | Select-String $pattern | Where-Object { $_.Line -match "LISTENING\s+(\d+)\s*$" }
    )
}

function Start-DevWindow {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command
    )
    $wd = $WorkingDirectory.Replace("'", "''")
    $cmd = $Command.Replace("'", "''")
    $safeTitle = $Title.Replace("'", "''")
    $line = "`$host.UI.RawUI.WindowTitle = '$safeTitle'; Set-Location '$wd'; $cmd"

    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", $line
    ) | Out-Null
}

Write-Host ""
Write-Host "=== Swigar dev stack ===" -ForegroundColor Cyan
Write-Host ""

if (-not $SkipStopApi) {
    Write-Host "[1/4] Free port 8000 ..." -ForegroundColor Gray
    & (Join-Path $Root "scripts\stop_api.ps1") | Out-Host
    if (Test-PortListening 8000) {
        Write-Warning "Port 8000 still in use. Run .\scripts\stop_dev_all.ps1 or end Python/uvicorn, then retry."
        exit 1
    }
} else {
    Write-Host "[1/4] Skip stop_api (-SkipStopApi)" -ForegroundColor Gray
}

$dashboardDir = Join-Path $Root "apps\debug-dashboard"
$gameDir = Join-Path $Root "TacticalDuel"

foreach ($pair in @(
        @{ Dir = $dashboardDir; Name = "debug-dashboard" }
        @{ Dir = $gameDir; Name = "TacticalDuel" }
    )) {
    if (-not (Test-Path (Join-Path $pair.Dir "node_modules"))) {
        Write-Warning "$($pair.Name): run npm install in $($pair.Dir)"
    }
}

Write-Host "[2/4] Start API (new window) ..." -ForegroundColor Gray
Start-DevWindow -Title "Swigar API :8000" -WorkingDirectory $Root -Command ".\scripts\run_api.ps1"

Write-Host "[3/4] Wait for /health ..." -ForegroundColor Gray
$healthUrl = "http://127.0.0.1:8000/health"
$ready = $false
$deadline = (Get-Date).AddSeconds($HealthWaitSec)
while ((Get-Date) -lt $deadline) {
    if (-not (Test-PortListening 8000)) {
        Start-Sleep -Seconds 2
        continue
    }
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -eq 200) {
            $ready = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
        continue
    }
    Start-Sleep -Seconds 2
}

if (-not $ready) {
    Write-Warning "API not ready within ${HealthWaitSec}s; opening frontends anyway (check API window)."
}
else {
    $llmLine = "API ready"
    try {
        $h = (Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5).Content | ConvertFrom-Json
        if ($h.llm_configured) {
            $llmLine = "API ready - LLM OK ($($h.llm_model))"
        }
        else {
            $llmLine = "API ready - LLM not configured"
        }
    }
    catch {
        $llmLine = "API ready"
    }
    Write-Host "      $llmLine" -ForegroundColor Green
}

Write-Host "[4/4] Start frontends (new windows) ..." -ForegroundColor Gray
Start-DevWindow -Title "Swigar Workbench :5173" -WorkingDirectory $dashboardDir -Command "npm run dev"
Start-Sleep -Seconds 1
Start-DevWindow -Title "TacticalDuel Game :5000" -WorkingDirectory $gameDir -Command "npm run dev"

Write-Host ""
Write-Host "Opened 3 windows:" -ForegroundColor Cyan
Write-Host "  API        http://127.0.0.1:8000/health"
Write-Host "  Workbench  http://127.0.0.1:5173"
Write-Host "  Game       http://127.0.0.1:5000"
Write-Host ""
Write-Host "Stop: Ctrl+C in each window, or .\scripts\stop_dev_all.ps1" -ForegroundColor Gray
Write-Host ""
