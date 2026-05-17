# Start Swigar API using project venv (avoids broken Anaconda onnxruntime).
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Missing .venv. Run: python -m venv .venv; .\.venv\Scripts\pip install -e . -e ./mempalace-reference"
    exit 1
}

function Test-PortHasListeners([int]$p) {
    $pattern = ":$p\s"
    $found = netstat -ano | Select-String $pattern | Where-Object { $_.Line -match "LISTENING\s+(\d+)\s*$" }
    return [bool]$found
}

$explicitPort = [bool]$env:API_PORT
$hostAddr = if ($env:API_HOST) { $env:API_HOST } else { "127.0.0.1" }
$port = if ($env:API_PORT) { $env:API_PORT } else { "8000" }

& (Join-Path $Root "scripts\stop_api.ps1")
if ($LASTEXITCODE -ne 0) {
    if (-not $explicitPort -and $port -eq "8000") {
        Write-Warning "Port 8000 still in use — starting on 8010 instead (matches debug-dashboard .env.development)."
        Write-Warning "To force 8000: free the port first, then run again. Game/TacticalDuel needs 8000 when you use that stack."
        $env:API_PORT = "8010"
        $port = "8010"
        & (Join-Path $Root "scripts\stop_api.ps1")
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Cannot start API: port $port is still in use. Fix with .\scripts\stop_api.ps1 or use .\scripts\run_api_workbench.ps1"
        exit 1
    }
}

if (Test-PortHasListeners ([int]$port)) {
    Write-Error "Port $port is still listening — aborting bind (avoids WinError 10048 and instant shutdown)."
    exit 1
}

$uvicornArgs = @(
    "-m", "uvicorn", "swigar_api.main:app",
    "--host", $hostAddr,
    "--port", $port
)

# Windows: --reload often leaves zombie listeners on 8000 (ECONNREFUSED). Opt-in only.
if ($env:SWIGAR_API_RELOAD -eq "1") {
    Write-Host "SWIGAR_API_RELOAD=1: hot reload enabled (services/api + packages only)"
    $uvicornArgs += @(
        "--reload",
        "--reload-dir", "services/api",
        "--reload-dir", "packages"
    )
} else {
    Write-Host "Single-process API on http://${hostAddr}:${port} (set SWIGAR_API_RELOAD=1 for hot reload)"
}

& $Python @uvicornArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
