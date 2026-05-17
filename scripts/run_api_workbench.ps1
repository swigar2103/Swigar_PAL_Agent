# Debug-dashboard dev API on 8010 — avoids zombie listeners stuck on 8000 (Windows + uvicorn --reload).
$Root = Split-Path -Parent $PSScriptRoot
$env:API_PORT = "8010"
$env:API_HOST = "127.0.0.1"
Write-Host "Workbench API: http://127.0.0.1:8010 (vite: apps/debug-dashboard/.env.development -> VITE_API_PROXY_TARGET)"
& (Join-Path $Root "scripts\run_api.ps1")
