# Stop Swigar API listeners and uvicorn worker processes.
$port = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }

function Get-ListenerPids([int]$p) {
    $pids = @()
    $pattern = ":$p\s"
    netstat -ano | Select-String $pattern | ForEach-Object {
        $line = $_.Line.Trim()
        if ($line -match "LISTENING\s+(\d+)\s*$") {
            $pids += [int]$Matches[1]
        }
    }
    return @($pids | Sort-Object -Unique)
}

function Show-ListenerProcess([int]$procId) {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "  PID ${procId}: $($proc.ProcessName)"
        return
    }
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    if ($cim) {
        $cmd = $cim.CommandLine
        if ($cmd.Length -gt 120) { $cmd = $cmd.Substring(0, 117) + "..." }
        Write-Host "  PID ${procId}: $($cim.Name) — $cmd"
    } else {
        Write-Warning "  PID ${procId}: process not found (stale netstat or another session — try Task Manager as Admin, or reboot)"
    }
}

function Stop-ListenerPid([int]$procId) {
    Show-ListenerProcess $procId
    taskkill /F /T /PID $procId 2>$null | Out-Null
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}

function Stop-UvicornWorkers {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^python(\.exe)?$' -and
            $_.CommandLine -and
            ($_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'swigar_api')
        } |
        ForEach-Object {
            Write-Host "Stopping uvicorn PID $($_.ProcessId)"
            taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

Stop-UvicornWorkers

for ($i = 0; $i -lt 10; $i++) {
    $pids = Get-ListenerPids $port
    if ($pids.Count -eq 0) {
        Write-Host "Port $port is free."
        exit 0
    }
    Write-Host "Stopping listeners on port ${port}: $($pids -join ', ')"
    $anyAlive = $false
    foreach ($procId in $pids) {
        if (Get-Process -Id $procId -ErrorAction SilentlyContinue) { $anyAlive = $true }
        Stop-ListenerPid $procId
    }
    if (-not $anyAlive) {
        Write-Warning "Listeners report dead PIDs only (ghost sockets on port $port). Skipping further retries."
        break
    }
    Start-Sleep -Seconds 1
}

$pids = Get-ListenerPids $port
if ($pids.Count -gt 0) {
    Write-Warning "Port $port still held by: $($pids -join ', ')"
    foreach ($procId in $pids) { Show-ListenerProcess $procId }
    Write-Warning "End the processes above in Task Manager (run as Admin if needed), or reboot."
    Write-Warning "For debug-dashboard without freeing 8000: .\scripts\run_api_workbench.ps1 (port 8010)"
    exit 1
}
Write-Host "Port $port is free."
exit 0
