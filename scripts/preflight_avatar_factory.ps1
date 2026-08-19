param(
  [string]$CharacterId = 'vaincriez-canary',
  [string]$ReferencePath = '',
  [string]$ComfyUIRoot = (Join-Path $env:USERPROFILE 'AI\ComfyUI_windows_portable\ComfyUI_windows_portable\ComfyUI'),
  [string]$ServerAddress = '127.0.0.1:8188'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Failures = New-Object System.Collections.Generic.List[string]

function Pass([string]$Message) { Write-Host "[OK] $Message" -ForegroundColor Green }
function Fail([string]$Message) { Write-Host "[KO] $Message" -ForegroundColor Red; $Failures.Add($Message) }
function Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }

Write-Host '=== Avatar Factory Production Preflight ===' -ForegroundColor Cyan

try { $py = python --version 2>&1; Pass "Python: $py" } catch { Fail 'Python not found in PATH' }
try { $nv = nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader 2>$null; if ($LASTEXITCODE -eq 0) { Pass "NVIDIA GPU: $nv" } else { Warn 'nvidia-smi unavailable' } } catch { Warn 'nvidia-smi unavailable' }

$blender = if ($env:BLENDER_EXE) { $env:BLENDER_EXE } else { 'blender' }
try {
  if ($env:BLENDER_EXE -and (Test-Path -LiteralPath $env:BLENDER_EXE -PathType Leaf)) { Pass "Blender: $env:BLENDER_EXE" }
  else { $b = Get-Command $blender -ErrorAction Stop; Pass "Blender: $($b.Source)" }
} catch { Fail 'Blender not found. Add blender.exe to PATH or define BLENDER_EXE.' }

$checkpoint = Join-Path $ComfyUIRoot 'models\checkpoints\hunyuan_3d_v2.1.safetensors'
if (Test-Path -LiteralPath $checkpoint -PathType Leaf) {
  $expected = '5f21e98a6cb99b13b5e224abaee33929570fff7af2b6a0060001559a04ba9d72'
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $checkpoint).Hash.ToLowerInvariant()
  if ($actual -eq $expected) { Pass 'Hunyuan3D 2.1 checkpoint + SHA256' } else { Fail 'Hunyuan3D checkpoint found but SHA256 is incorrect' }
} else { Fail "Hunyuan3D checkpoint missing: $checkpoint" }

try {
  $stats = Invoke-RestMethod -Method Get -Uri "http://$ServerAddress/system_stats" -TimeoutSec 5
  Pass "ComfyUI API: http://$ServerAddress"
  $info = Invoke-RestMethod -Method Get -Uri "http://$ServerAddress/object_info" -TimeoutSec 30
  $required = @('ImageOnlyCheckpointLoader','LoadImage','ModelSamplingAuraFlow','CLIPVisionEncode','Hunyuan3Dv2Conditioning','EmptyLatentHunyuan3Dv2','KSampler','VAEDecodeHunyuan3D','VoxelToMesh','SaveGLB')
  $available = @($info.PSObject.Properties.Name)
  $missing = @($required | Where-Object { $_ -notin $available })
  if ($missing.Count -eq 0) { Pass 'Required ComfyUI Hunyuan3D nodes available' } else { Fail "Missing ComfyUI nodes: $($missing -join ', ')" }
} catch { Fail "ComfyUI unavailable or incomplete on http://${ServerAddress}: $($_.Exception.Message)" }

$manifestPath = Join-Path $Root "characters\$CharacterId\manifest.json"
if (Test-Path -LiteralPath $manifestPath -PathType Leaf) { Pass "Character manifest: $CharacterId" } else { Fail "Character manifest missing: $manifestPath" }

if ($ReferencePath) {
  if (Test-Path -LiteralPath $ReferencePath -PathType Leaf) {
    $size = (Get-Item -LiteralPath $ReferencePath).Length
    $sizeKb = [math]::Round(($size / 1KB), 1)
    if ($size -ge 10000) { Pass "Reference supplied: $ReferencePath - $sizeKb KB" } else { Fail 'Reference image is too small or invalid' }
  } else { Fail "Reference image supplied but not found: $ReferencePath" }
} else {
  $canonicalReference = Join-Path $Root "characters\$CharacterId\reference.png"
  if (Test-Path -LiteralPath $canonicalReference -PathType Leaf) {
    $size = (Get-Item -LiteralPath $canonicalReference).Length
    $sizeKb = [math]::Round(($size / 1KB), 1)
    if ($size -ge 10000) { Pass "Canonical reference available: $canonicalReference - $sizeKb KB" } else { Warn 'Canonical reference is too small; use Cockpit upload before starting a job.' }
  } else {
    Warn 'No local reference preloaded. This is normal when the image will be uploaded from Cockpit > Avatar Factory after services 8791/8792 start.'
  }
}

$drive = Get-PSDrive -Name C -ErrorAction SilentlyContinue
if ($drive) {
  $freeGb = [math]::Round(($drive.Free / 1GB), 1)
  if ($freeGb -ge 25) { Pass "Free disk space C: $freeGb GB" } else { Fail "Insufficient disk space: $freeGb GB - minimum 25 GB" }
}

try {
  python "$PSScriptRoot\validate_avatar_factory.py"
  if ($LASTEXITCODE -eq 0) { Pass 'Avatar Factory repository contract' } else { Fail 'Repository validation failed' }
} catch { Fail "Repository validation unavailable: $($_.Exception.Message)" }

Write-Host ''
if ($Failures.Count -gt 0) {
  Write-Host "PRECHECK FAILED - $($Failures.Count) blocker(s)" -ForegroundColor Red
  $Failures | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
  exit 1
}
Write-Host 'PRECHECK PASSED - station ready. The reference can now be uploaded from the Cockpit before starting a job.' -ForegroundColor Green
exit 0
