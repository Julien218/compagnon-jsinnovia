param(
    [string]$ComfyUIRoot = $(if ($env:COMFYUI_ROOT) { $env:COMFYUI_ROOT } else { Join-Path $env:USERPROFILE 'AI\ComfyUI_windows_portable\ComfyUI_windows_portable\ComfyUI' }),
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$checkpointName = 'hunyuan_3d_v2.1.safetensors'
$checkpointUrl = 'https://huggingface.co/Comfy-Org/hunyuan3D_2.1_repackaged/resolve/main/hunyuan_3d_v2.1.safetensors'
$expectedSha256 = '5f21e98a6cb99b13b5e224abaee33929570fff7af2b6a0060001559a04ba9d72'
$checkpointDir = Join-Path $ComfyUIRoot 'models\checkpoints'
$checkpointPath = Join-Path $checkpointDir $checkpointName

Write-Host "Elyna / Hunyuan3D 2.1 checkpoint setup" -ForegroundColor Cyan
Write-Host "ComfyUI root: $ComfyUIRoot"

if (-not (Test-Path $ComfyUIRoot)) {
    throw "ComfyUI root not found: $ComfyUIRoot. Re-run with -ComfyUIRoot <path>."
}

New-Item -ItemType Directory -Path $checkpointDir -Force | Out-Null

$driveName = [System.IO.Path]::GetPathRoot($checkpointPath).TrimEnd('\').TrimEnd(':')
if ($driveName) {
    $drive = Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue
    if ($drive) {
        $freeGiB = [math]::Round($drive.Free / 1GB, 1)
        Write-Host "Free disk space: $freeGiB GiB"
        if ($drive.Free -lt 10GB) {
            throw 'At least 10 GiB of free disk space is required before downloading the checkpoint.'
        }
    }
}

if (Test-Path $checkpointPath) {
    $existingHash = (Get-FileHash -Algorithm SHA256 -Path $checkpointPath).Hash.ToLowerInvariant()
    if ($existingHash -eq $expectedSha256) {
        Write-Host 'Checkpoint already present and SHA256 is valid.' -ForegroundColor Green
        exit 0
    }

    if (-not $Force) {
        throw "Checkpoint exists but SHA256 is incorrect. Re-run with -Force to replace it."
    }

    Remove-Item -Force $checkpointPath
}

Write-Host "Downloading $checkpointName (large file; this can take a while)..." -ForegroundColor Yellow

$bits = Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue
if ($bits) {
    Start-BitsTransfer -Source $checkpointUrl -Destination $checkpointPath -DisplayName 'Hunyuan3D 2.1 checkpoint'
} else {
    Invoke-WebRequest -Uri $checkpointUrl -OutFile $checkpointPath -UseBasicParsing
}

Write-Host 'Verifying SHA256...' -ForegroundColor Yellow
$downloadedHash = (Get-FileHash -Algorithm SHA256 -Path $checkpointPath).Hash.ToLowerInvariant()
if ($downloadedHash -ne $expectedSha256) {
    Remove-Item -Force $checkpointPath
    throw "SHA256 verification failed. Download removed. Expected $expectedSha256, got $downloadedHash."
}

Write-Host 'Checkpoint installed and verified.' -ForegroundColor Green
Write-Host "Path: $checkpointPath"

$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    Write-Host ''
    Write-Host 'GPU memory information:' -ForegroundColor Cyan
    & nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
}

Write-Host ''
Write-Host 'Next:' -ForegroundColor Cyan
Write-Host '1. Copy 00_phenix_companion_officiel_reference.png into ComfyUI\input.'
Write-Host '2. Import workflows\comfyui\elyna_hunyuan3d_shape.json into ComfyUI.'
Write-Host '3. Run the diagnostic 1024 preset first.'
