$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $env:COMFYUI_ROOT) {
  $desktopComfyUI = Join-Path $env:LOCALAPPDATA 'Comfy-Desktop\ComfyUI-Installs\Comfyui\ComfyUI'
  if (Test-Path -LiteralPath $desktopComfyUI -PathType Container) {
    $env:COMFYUI_ROOT = $desktopComfyUI
  }
}

if (-not $env:BLENDER_EXE) {
  $blenderCandidates = @(
    (Join-Path $env:ProgramFiles 'Blender Foundation\Blender 5.2\blender.exe'),
    (Join-Path $env:ProgramFiles 'Blender Foundation\Blender 5.1\blender.exe'),
    (Join-Path $env:ProgramFiles 'Blender Foundation\Blender 5.0\blender.exe')
  )
  $env:BLENDER_EXE = $blenderCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}

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

Write-Host 'Starting secure reference image upload API on http://127.0.0.1:8792' -ForegroundColor Green
$uploadScript = Join-Path $PSScriptRoot 'avatar_reference_upload_server.py'
Start-Process -WindowStyle Hidden -FilePath 'python' -ArgumentList @('-u', "`"$uploadScript`"")

Write-Host 'Starting secure 3D preview API on http://127.0.0.1:8793' -ForegroundColor Green
$previewScript = Join-Path $PSScriptRoot 'avatar_preview_server.py'
Start-Process -WindowStyle Hidden -FilePath 'python' -ArgumentList @('-u', "`"$previewScript`"")

if ($env:COCKPIT_URL -and $env:FINOPS_INGEST_KEY) {
  Write-Host 'Starting automatic FinOps synchronization...' -ForegroundColor Green
  $finopsScript = Join-Path $PSScriptRoot 'sync_finops.py'
  Start-Process -WindowStyle Hidden -FilePath 'python' -ArgumentList @('-u', "`"$finopsScript`"", '--watch')
} else {
  Write-Warning 'FinOps cloud sync disabled until COCKPIT_URL and FINOPS_INGEST_KEY are configured.'
}

Write-Host 'Starting Avatar Factory API on http://127.0.0.1:8791'
Write-Host 'Reference upload API available on http://127.0.0.1:8792'
Write-Host '3D preview API available on http://127.0.0.1:8793'
python "$PSScriptRoot/avatar_factory_server.py"
