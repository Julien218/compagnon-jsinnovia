param(
    [ValidateSet('diagnostic', 'production')]
    [string]$Preset = 'diagnostic',
    [string]$ComfyUIRoot = $(if ($env:COMFYUI_ROOT) { $env:COMFYUI_ROOT } else { Join-Path $env:USERPROFILE 'AI\ComfyUI_windows_portable\ComfyUI_windows_portable\ComfyUI' }),
    [string]$ServerAddress = '127.0.0.1:8188',
    [int]$StartupTimeoutSeconds = 180,
    [int]$RunTimeoutMinutes = 90,
    [switch]$ForceCheckpoint
)

$ErrorActionPreference = 'Stop'

$setupScript = Join-Path $PSScriptRoot 'setup_hunyuan3d_checkpoint.ps1'
$runnerScript = Join-Path $PSScriptRoot 'run_elyna_comfyui.ps1'
$baseUrl = "http://$ServerAddress"

function Test-ComfyUIApi {
    try {
        $null = Invoke-RestMethod -Method Get -Uri "$baseUrl/system_stats" -TimeoutSec 5
        return $true
    } catch {
        return $false
    }
}

function Find-ComfyUILauncher([string]$Root) {
    $portableRoot = Split-Path -Parent $Root
    $candidates = @(
        (Join-Path $portableRoot 'run_nvidia_gpu.bat'),
        (Join-Path $portableRoot 'run_nvidia_gpu_fast_fp16_accumulation.bat')
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    return $null
}

Write-Host '=============================================' -ForegroundColor DarkCyan
Write-Host ' Elyna 3D — bootstrap local JS-Innov.IA' -ForegroundColor Cyan
Write-Host '=============================================' -ForegroundColor DarkCyan
Write-Host "Preset : $Preset"
Write-Host "ComfyUI root : $ComfyUIRoot"
Write-Host "API : $baseUrl"
Write-Host ''

if (-not (Test-Path -LiteralPath $ComfyUIRoot -PathType Container)) {
    throw "ComfyUI root not found: $ComfyUIRoot"
}

if (-not (Test-Path -LiteralPath $setupScript -PathType Leaf)) {
    throw "Setup script missing: $setupScript"
}
if (-not (Test-Path -LiteralPath $runnerScript -PathType Leaf)) {
    throw "Runner script missing: $runnerScript"
}

Write-Host '[1/4] Checkpoint Hunyuan3D 2.1' -ForegroundColor Cyan
if ($ForceCheckpoint) {
    & $setupScript -ComfyUIRoot $ComfyUIRoot -Force
} else {
    & $setupScript -ComfyUIRoot $ComfyUIRoot
}

Write-Host ''
Write-Host '[2/4] ComfyUI API' -ForegroundColor Cyan
if (-not (Test-ComfyUIApi)) {
    $launcher = Find-ComfyUILauncher $ComfyUIRoot
    if (-not $launcher) {
        throw "ComfyUI is not running and no NVIDIA portable launcher was found next to $ComfyUIRoot. Start ComfyUI manually, then rerun this script."
    }

    $workingDirectory = Split-Path -Parent $launcher
    Write-Host "Starting ComfyUI with: $launcher" -ForegroundColor Yellow
    Start-Process -FilePath $launcher -WorkingDirectory $workingDirectory | Out-Null

    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if (Test-ComfyUIApi) {
            break
        }
        Write-Host 'Waiting for ComfyUI API...' -ForegroundColor DarkGray
    }

    if (-not (Test-ComfyUIApi)) {
        throw "ComfyUI did not become reachable within $StartupTimeoutSeconds seconds at $baseUrl. Check the ComfyUI console for startup errors."
    }
}
Write-Host 'ComfyUI API: ready' -ForegroundColor Green

Write-Host ''
Write-Host '[3/4] Elyna Hunyuan3D generation' -ForegroundColor Cyan
& $runnerScript -Preset $Preset -ServerAddress $ServerAddress -ComfyUIRoot $ComfyUIRoot -TimeoutMinutes $RunTimeoutMinutes

Write-Host ''
Write-Host '[4/4] Pipeline stage complete' -ForegroundColor Green
Write-Host 'If a GLB candidate was generated, review it visually before Blender cleanup/retopology/rigging.' -ForegroundColor Yellow
Write-Host 'Do not activate the site VRM until the final model passes the validated-model-only gate.' -ForegroundColor Yellow
