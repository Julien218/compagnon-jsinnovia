param(
    [ValidateSet('diagnostic', 'production')]
    [string]$Preset = 'diagnostic',
    [string]$ServerAddress = '127.0.0.1:8188',
    [string]$ComfyUIRoot = $(if ($env:COMFYUI_ROOT) { $env:COMFYUI_ROOT } else { Join-Path $env:USERPROFILE 'AI\ComfyUI_windows_portable\ComfyUI_windows_portable\ComfyUI' }),
    [string]$ComfyUISharedRoot = $env:COMFYUI_SHARED_ROOT,
    [int]$TimeoutMinutes = 90
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiWorkflowPath = Join-Path $repoRoot 'workflows\comfyui\elyna_hunyuan3d_shape_api.json'
$checkpointName = 'hunyuan_3d_v2.1.safetensors'
$expectedSha256 = '5f21e98a6cb99b13b5e224abaee33929570fff7af2b6a0060001559a04ba9d72'
$checkpointPath = Join-Path $ComfyUIRoot "models\checkpoints\$checkpointName"
if (-not $ComfyUISharedRoot) {
    $desktopShared = Join-Path $env:LOCALAPPDATA 'Comfy-Desktop\ComfyUI-Shared'
    if (Test-Path -LiteralPath $desktopShared -PathType Container) { $ComfyUISharedRoot = $desktopShared }
}
$inputDir = if ($ComfyUISharedRoot) { Join-Path $ComfyUISharedRoot 'input' } else { Join-Path $ComfyUIRoot 'input' }
$canonicalImageName = '00_phenix_companion_officiel_reference.png'
$canonicalImagePath = Join-Path $inputDir $canonicalImageName
$fallbackImagePath = Join-Path $inputDir 'elyna-reference.png'
$outputDir = if ($ComfyUISharedRoot) { Join-Path $ComfyUISharedRoot 'output' } else { Join-Path $ComfyUIRoot 'output' }
$baseUrl = "http://$ServerAddress"

function Assert-File([string]$Path, [string]$Message) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw $Message
    }
}

function Get-Sha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

Write-Host 'Elyna — Hunyuan3D local runner' -ForegroundColor Cyan
Write-Host "Preset: $Preset"
Write-Host "ComfyUI: $baseUrl"

if (-not (Test-Path -LiteralPath $ComfyUIRoot -PathType Container)) {
    throw "ComfyUI root not found: $ComfyUIRoot"
}

Assert-File $apiWorkflowPath "API workflow missing: $apiWorkflowPath"
Assert-File $checkpointPath "Checkpoint missing: $checkpointPath. Run scripts\setup_hunyuan3d_checkpoint.ps1 first."

$checkpointHash = Get-Sha256 $checkpointPath
if ($checkpointHash -ne $expectedSha256) {
    throw "Checkpoint SHA256 is invalid. Expected $expectedSha256, got $checkpointHash."
}
Write-Host 'Checkpoint SHA256: OK' -ForegroundColor Green

if (-not (Test-Path -LiteralPath $canonicalImagePath -PathType Leaf)) {
    if (Test-Path -LiteralPath $fallbackImagePath -PathType Leaf) {
        Write-Host "Canonical filename missing; copying existing elyna-reference.png to $canonicalImageName" -ForegroundColor Yellow
        Copy-Item -LiteralPath $fallbackImagePath -Destination $canonicalImagePath -Force
    } else {
        throw "Reference image missing. Put $canonicalImageName (or elyna-reference.png) in $inputDir."
    }
}

try {
    $null = Invoke-RestMethod -Method Get -Uri "$baseUrl/system_stats" -TimeoutSec 10
} catch {
    throw "ComfyUI is not reachable at $baseUrl. Start ComfyUI and retry. Details: $($_.Exception.Message)"
}
Write-Host 'ComfyUI API: reachable' -ForegroundColor Green

try {
    $objectInfo = Invoke-RestMethod -Method Get -Uri "$baseUrl/object_info" -TimeoutSec 30
} catch {
    throw "Unable to read ComfyUI node registry: $($_.Exception.Message)"
}

$requiredNodes = @(
    'ImageOnlyCheckpointLoader',
    'LoadImage',
    'ModelSamplingAuraFlow',
    'CLIPVisionEncode',
    'Hunyuan3Dv2Conditioning',
    'EmptyLatentHunyuan3Dv2',
    'KSampler',
    'VAEDecodeHunyuan3D',
    'VoxelToMesh',
    'SaveGLB'
)

$availableNodeNames = @($objectInfo.PSObject.Properties.Name)
$missingNodes = @($requiredNodes | Where-Object { $_ -notin $availableNodeNames })
if ($missingNodes.Count -gt 0) {
    throw "ComfyUI is missing required Hunyuan3D nodes: $($missingNodes -join ', '). Update ComfyUI before running Elyna."
}
Write-Host 'Required Hunyuan3D nodes: OK' -ForegroundColor Green

$prompt = Get-Content -LiteralPath $apiWorkflowPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Preset -eq 'production') {
    $prompt.'4'.inputs.resolution = 2048
    $prompt.'10'.inputs.filename_prefix = 'Elyna/elyna_shape_production_2048'
    Write-Host 'WARNING: production 2048 uses substantially more VRAM. The official Hunyuan3D 2.1 guidance is about 10 GiB of VRAM for shape generation alone. Only try this after the 1024 diagnostic succeeds; on lower-VRAM hardware the run may fail even with memory offload.' -ForegroundColor Yellow
} else {
    $prompt.'4'.inputs.resolution = 1024
    $prompt.'10'.inputs.filename_prefix = 'Elyna/elyna_shape_low_vram_1024'
}

$clientId = [guid]::NewGuid().ToString()
$payload = @{
    prompt = $prompt
    client_id = $clientId
} | ConvertTo-Json -Depth 100

$startTime = Get-Date
Write-Host 'Submitting workflow...' -ForegroundColor Cyan
try {
    $queued = Invoke-RestMethod -Method Post -Uri "$baseUrl/prompt" -ContentType 'application/json' -Body $payload -TimeoutSec 60
} catch {
    $detail = $_.ErrorDetails.Message
    if (-not $detail) { $detail = $_.Exception.Message }
    throw "ComfyUI rejected the workflow: $detail"
}

if (-not $queued.prompt_id) {
    throw 'ComfyUI did not return a prompt_id.'
}

$promptId = [string]$queued.prompt_id
Write-Host "Queued prompt: $promptId" -ForegroundColor Green

$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
$historyItem = $null
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 5
    try {
        $history = Invoke-RestMethod -Method Get -Uri "$baseUrl/history/$promptId" -TimeoutSec 30
        if ($history -and $history.PSObject.Properties.Name -contains $promptId) {
            $historyItem = $history.$promptId
            break
        }
    } catch {
        Write-Host 'Waiting for ComfyUI history...' -ForegroundColor DarkGray
    }
}

if (-not $historyItem) {
    throw "Timed out after $TimeoutMinutes minutes waiting for prompt $promptId. The job may still be running in ComfyUI."
}

if ($historyItem.status -and $historyItem.status.status_str -and $historyItem.status.status_str -ne 'success') {
    $messages = $historyItem.status.messages | ConvertTo-Json -Depth 10 -Compress
    throw "ComfyUI completed with status '$($historyItem.status.status_str)'. Messages: $messages"
}

Write-Host 'ComfyUI execution completed.' -ForegroundColor Green

$newGlbs = @()
if (Test-Path -LiteralPath $outputDir) {
    $newGlbs = @(Get-ChildItem -LiteralPath $outputDir -Filter '*.glb' -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $startTime.AddMinutes(-1) } |
        Sort-Object LastWriteTime -Descending)
}

if ($newGlbs.Count -gt 0) {
    Write-Host 'Generated GLB candidate(s):' -ForegroundColor Cyan
    $newGlbs | Select-Object -First 5 | ForEach-Object {
        $sizeMiB = [math]::Round($_.Length / 1MB, 2)
        Write-Host " - $($_.FullName) ($sizeMiB MiB)"
    }
    Write-Host ''
    Write-Host 'This is a RAW shape candidate, not the final VRM. Review silhouette/headset/mic/emblem/wings before Blender retopology and rigging.' -ForegroundColor Yellow
} else {
    Write-Host "Prompt completed but no recent .glb was found under $outputDir. Inspect ComfyUI history for SaveGLB output metadata." -ForegroundColor Yellow
}
