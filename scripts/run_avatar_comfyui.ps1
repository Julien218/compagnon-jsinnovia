param(
    [Parameter(Mandatory=$true)][string]$CharacterId,
    [Parameter(Mandatory=$true)][string]$ReferencePath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [ValidateSet('diagnostic','production')][string]$Preset = 'diagnostic',
    [string]$ServerAddress = '127.0.0.1:8188',
    [string]$ComfyUIRoot = $(if ($env:COMFYUI_ROOT) { $env:COMFYUI_ROOT } else { Join-Path $env:USERPROFILE 'AI\ComfyUI_windows_portable\ComfyUI_windows_portable\ComfyUI' }),
    [int]$TimeoutMinutes = 90
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$workflowPath = Join-Path $repoRoot 'workflows\comfyui\avatar_hunyuan3d_shape_api.json'
$checkpointName = 'hunyuan_3d_v2.1.safetensors'
$expectedSha256 = '5f21e98a6cb99b13b5e224abaee33929570fff7af2b6a0060001559a04ba9d72'
$checkpointPath = Join-Path $ComfyUIRoot "models\checkpoints\$checkpointName"
$inputDir = Join-Path $ComfyUIRoot 'input'
$outputDir = Join-Path $ComfyUIRoot 'output'
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
Assert-File $workflowPath "Generic API workflow missing: $workflowPath"
Assert-File $checkpointPath "Checkpoint missing: $checkpointPath"
$hash = Get-Sha256 $checkpointPath
if ($hash -ne $expectedSha256) { throw "Checkpoint SHA256 mismatch." }

try { $null = Invoke-RestMethod -Method Get -Uri "$baseUrl/system_stats" -TimeoutSec 10 } catch { throw "ComfyUI unavailable at $baseUrl" }
$objectInfo = Invoke-RestMethod -Method Get -Uri "$baseUrl/object_info" -TimeoutSec 30
$requiredNodes = @('ImageOnlyCheckpointLoader','LoadImage','ModelSamplingAuraFlow','CLIPVisionEncode','Hunyuan3Dv2Conditioning','EmptyLatentHunyuan3Dv2','KSampler','VAEDecodeHunyuan3D','VoxelToMesh','SaveGLB')
$available = @($objectInfo.PSObject.Properties.Name)
$missing = @($requiredNodes | Where-Object { $_ -notin $available })
if ($missing.Count -gt 0) { throw "Missing ComfyUI nodes: $($missing -join ', ')" }

$inputName = "avatarfactory_$($CharacterId -replace '[^a-zA-Z0-9_-]','_')_$([guid]::NewGuid().ToString('N')).png"
$inputPath = Join-Path $inputDir $inputName
Copy-Item -LiteralPath $ReferencePath -Destination $inputPath -Force

$prompt = Get-Content -LiteralPath $workflowPath -Raw -Encoding UTF8 | ConvertFrom-Json
$prompt.'2'.inputs.image = $inputName
if ($Preset -eq 'production') { $prompt.'4'.inputs.resolution = 2048 } else { $prompt.'4'.inputs.resolution = 1024 }
$prefixSafe = ($CharacterId -replace '[^a-zA-Z0-9_-]','_')
$prompt.'10'.inputs.filename_prefix = "AvatarFactory/$prefixSafe/$prefixSafe-$Preset"
$prompt.'7'.inputs.seed = Get-Random -Minimum 1 -Maximum 2147483646

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

$candidates = @(Get-ChildItem -LiteralPath $outputDir -Filter '*.glb' -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $startTime.AddMinutes(-1) } | Sort-Object LastWriteTime -Descending)
if ($candidates.Count -lt 1) { throw 'No new GLB found after successful ComfyUI job' }
$destination = [System.IO.Path]::GetFullPath($OutputPath)
$destinationDir = Split-Path -Parent $destination
New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
Copy-Item -LiteralPath $candidates[0].FullName -Destination $destination -Force
Remove-Item -LiteralPath $inputPath -Force -ErrorAction SilentlyContinue
Write-Host "AVATAR_FACTORY_OUTPUT=$destination"
