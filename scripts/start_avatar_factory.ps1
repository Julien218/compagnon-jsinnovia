$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host '=== JS-Innov.IA Avatar Factory ===' -ForegroundColor Cyan
Write-Host 'Checking Python...'
python --version

Write-Host 'Checking ComfyUI endpoint...'
try {
  $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8188/system_stats' -UseBasicParsing -TimeoutSec 3
  Write-Host 'ComfyUI online' -ForegroundColor Green
} catch {
  Write-Warning 'ComfyUI not reachable on 127.0.0.1:8188. Avatar Factory will start, but 3D jobs will fail until ComfyUI is online.'
}

if ($env:COCKPIT_URL -and $env:FINOPS_INGEST_KEY) {
  Write-Host 'Starting automatic FinOps synchronization...' -ForegroundColor Green
  Start-Process -WindowStyle Hidden -FilePath 'python' -ArgumentList @("$PSScriptRoot/sync_finops.py", '--watch')
} else {
  Write-Warning 'FinOps cloud sync disabled until COCKPIT_URL and FINOPS_INGEST_KEY are configured.'
}

Write-Host 'Starting Avatar Factory API on http://127.0.0.1:8791'
python "$PSScriptRoot/avatar_factory_server.py"
