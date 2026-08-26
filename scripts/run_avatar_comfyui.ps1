param(
    [Parameter(Mandatory=$true)][string]$CharacterId,
    [Parameter(Mandatory=$true)][string]$ReferencePath,
    [string]$LeftReferencePath,
    [string]$BackReferencePath,
    [string]$RightReferencePath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [ValidateSet('diagnostic','production')][string]$Preset = 'diagnostic',
    [string]$ServerAddress = '127.0.0.1:8188',
    [string]$ComfyUIRoot = $(if ($env:COMFYUI_ROOT) { $env:COMFYUI_ROOT } else { Join-Path $env:USERPROFILE 'AI\ComfyUI_windows_portable\ComfyUI_windows_portable\ComfyUI' }),
    [string]$ComfyUISharedRoot = $env:COMFYUI_SHARED_ROOT,
    [int]$TimeoutMinutes = 90,
    [ValidateRange(1,2147483646)][long]$Seed = 2182026
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$singleViewWorkflow = Join-Path $repoRoot 'workflows\comfyui\avatar_hunyuan3d_shape_api.json'
$multiViewWorkflow = Join-Path $repoRoot 'workflows\comfyui\avatar_hunyuan3d_multiview_api.json'
$multiViewPaths = @($LeftReferencePath, $BackReferencePath, $RightReferencePath) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
$useMultiView = $multiViewPaths.Count -gt 0
if ($useMultiView -and $multiViewPaths.Count -ne 3) { throw 'Multiview mode requires front, left, back and right references.' }
$workflowPath = if ($useMultiView) { $multiViewWorkflow } else { $singleViewWorkflow }
$checkpointName = if ($useMultiView) { 'hunyuan3d-dit-v2-mv_fp16.safetensors' } else { 'hunyuan_3d_v2.1.safetensors' }
$expectedSha256 = if ($useMultiView) { 'd36f5881bcdc56726b73e517cd444c13c60732431622da7268145355c8d38e9c' } else { '5f21e98a6cb99b13b5e224abaee33929570fff7af2b6a0060001559a04ba9d72' }
$checkpointPath = Join-Path $ComfyUIRoot "models\checkpoints\$checkpointName"
if (-not $ComfyUISharedRoot) {
    $desktopShared = Join-Path $env:LOCALAPPDATA 'Comfy-Desktop\ComfyUI-Shared'
    if (Test-Path -LiteralPath $desktopShared -PathType Container) { $ComfyUISharedRoot = $desktopShared }
}
$inputDir = if ($ComfyUISharedRoot) { Join-Path $ComfyUISharedRoot 'input' } else { Join-Path $ComfyUIRoot 'input' }
$outputDir = if ($ComfyUISharedRoot) { Join-Path $ComfyUISharedRoot 'output' } else { Join-Path $ComfyUIRoot 'output' }
$baseUrl = "http://$ServerAddress"

function Assert-File([string]$Path,[string]$Message) { if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw $Message } }
function Get-Sha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

Assert-File $ReferencePath "Avatar reference missing: $ReferencePath"
if ($useMultiView) {
    Assert-File $LeftReferencePath "Avatar left reference missing: $LeftReferencePath"
    Assert-File $BackReferencePath "Avatar back reference missing: $BackReferencePath"
    Assert-File $RightReferencePath "Avatar right reference missing: $RightReferencePath"
}
Assert-File $workflowPath "Generic API workflow missing: $workflowPath"
Assert-File $checkpointPath "Checkpoint missing: $checkpointPath"
if (-not (Test-Path -LiteralPath $inputDir -PathType Container)) { throw "ComfyUI input directory missing: $inputDir" }
if (-not (Test-Path -LiteralPath $outputDir -PathType Container)) { throw "ComfyUI output directory missing: $outputDir" }
$hash = Get-Sha256 $checkpointPath
if ($hash -ne $expectedSha256) { throw "Checkpoint SHA256 mismatch." }

try { $null = Invoke-RestMethod -Method Get -Uri "$baseUrl/system_stats" -TimeoutSec 10 } catch { throw "ComfyUI unavailable at $baseUrl" }
$objectInfo = Invoke-RestMethod -Method Get -Uri "$baseUrl/object_info" -TimeoutSec 30
$conditioningNode = if ($useMultiView) { 'Hunyuan3Dv2ConditioningMultiView' } else { 'Hunyuan3Dv2Conditioning' }
$requiredNodes = @('ImageOnlyCheckpointLoader','LoadImage','ModelSamplingAuraFlow','CLIPVisionEncode',$conditioningNode,'EmptyLatentHunyuan3Dv2','KSampler','VAEDecodeHunyuan3D','VoxelToMesh','SaveGLB')
if ($useMultiView) { $requiredNodes += 'FluxGuidance' }
$available = @($objectInfo.PSObject.Properties.Name)
$missing = @($requiredNodes | Where-Object { $_ -notin $available })
if ($missing.Count -gt 0) { throw "Missing ComfyUI nodes: $($missing -join ', ')" }
if ($useMultiView) {
    $multiViewInputs = @($objectInfo.Hunyuan3Dv2ConditioningMultiView.input.optional.PSObject.Properties.Name)
    $missingInputs = @('front','left','back','right') | Where-Object { $_ -notin $multiViewInputs }
    if ($missingInputs.Count -gt 0) { throw "Hunyuan3D multiview inputs missing: $($missingInputs -join ', ')" }
}

$inputExtension = [System.IO.Path]::GetExtension($ReferencePath).ToLowerInvariant()
$inputName = "avatarfactory_$($CharacterId -replace '[^a-zA-Z0-9_-]','_')_front_$([guid]::NewGuid().ToString('N'))$inputExtension"
$inputPath = Join-Path $inputDir $inputName
Copy-Item -LiteralPath $ReferencePath -Destination $inputPath -Force
$viewInputs = @{}
if ($useMultiView) {
    foreach ($view in @(@{ Name='left'; Path=$LeftReferencePath }, @{ Name='back'; Path=$BackReferencePath }, @{ Name='right'; Path=$RightReferencePath })) {
        $extension = [System.IO.Path]::GetExtension($view.Path).ToLowerInvariant()
        $name = "avatarfactory_$($CharacterId -replace '[^a-zA-Z0-9_-]','_')_$($view.Name)_$([guid]::NewGuid().ToString('N'))$extension"
        $path = Join-Path $inputDir $name
        Copy-Item -LiteralPath $view.Path -Destination $path -Force
        $viewInputs[$view.Name] = @{ Name=$name; Path=$path }
    }
}

$prompt = Get-Content -LiteralPath $workflowPath -Raw -Encoding UTF8 | ConvertFrom-Json
$prompt.'2'.inputs.image = $inputName
if ($useMultiView) {
    $prompt.'5'.inputs.image = $viewInputs.right.Name
    $prompt.'16'.inputs.image = $viewInputs.left.Name
    $prompt.'17'.inputs.image = $viewInputs.back.Name
}
if ($Preset -eq 'production') {
    $prompt.'4'.inputs.resolution = 2048
    if ($useMultiView) {
        $prompt.'8'.inputs.num_chunks = 8000
        $prompt.'8'.inputs.octree_resolution = 256
    }
} else {
    $prompt.'4'.inputs.resolution = 1024
}
$prefixSafe = ($CharacterId -replace '[^a-zA-Z0-9_-]','_')
$prompt.'10'.inputs.filename_prefix = "AvatarFactory/$prefixSafe/$prefixSafe-$Preset"
$prompt.'7'.inputs.seed = $Seed

$payload = @{ prompt=$prompt; client_id=[guid]::NewGuid().ToString() } | ConvertTo-Json -Depth 100
$startTime = Get-Date
$queued = Invoke-RestMethod -Method Post -Uri "$baseUrl/prompt" -ContentType 'application/json' -Body $payload -TimeoutSec 60
if (-not $queued.prompt_id) { throw 'ComfyUI did not return prompt_id' }
$promptId = [string]$queued.prompt_id
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
$historyItem = $null
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 5
  try {
    $history = Invoke-RestMethod -Method Get -Uri "$baseUrl/history/$promptId" -TimeoutSec 30
    if ($history -and $history.PSObject.Properties.Name -contains $promptId) { $historyItem = $history.$promptId; break }
  } catch {}
}
if (-not $historyItem) { throw "Timed out waiting for $promptId" }
if ($historyItem.status -and $historyItem.status.status_str -and $historyItem.status.status_str -ne 'success') { throw "ComfyUI status: $($historyItem.status.status_str)" }

$reported = @($historyItem.outputs.'10'.'3d')
$candidates = @()
foreach ($item in $reported) {
  if (-not $item.filename) { continue }
  $candidate = if ($item.subfolder) { Join-Path (Join-Path $outputDir $item.subfolder) $item.filename } else { Join-Path $outputDir $item.filename }
  if (Test-Path -LiteralPath $candidate -PathType Leaf) { $candidates += Get-Item -LiteralPath $candidate }
}
if ($candidates.Count -lt 1) {
  $candidates = @(Get-ChildItem -LiteralPath $outputDir -Filter '*.glb' -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $startTime.AddMinutes(-1) } | Sort-Object LastWriteTime -Descending)
}
if ($candidates.Count -lt 1) { throw 'SaveGLB completed without a GLB file. The generated voxel mesh may be empty.' }
$destination = [System.IO.Path]::GetFullPath($OutputPath)
$destinationDir = Split-Path -Parent $destination
New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
Copy-Item -LiteralPath $candidates[0].FullName -Destination $destination -Force
Remove-Item -LiteralPath $inputPath -Force -ErrorAction SilentlyContinue
foreach ($view in $viewInputs.Values) { Remove-Item -LiteralPath $view.Path -Force -ErrorAction SilentlyContinue }
Write-Host "AVATAR_FACTORY_OUTPUT=$destination"
