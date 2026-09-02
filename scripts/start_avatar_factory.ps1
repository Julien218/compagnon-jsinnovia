param(
  [ValidateRange(5,120)]
  [int]$StartupTimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $env:COMFYUI_ROOT) {
  $desktopComfyUI = Join-Path $env:LOCALAPPDATA 'Comfy-Desktop\ComfyUI-Installs\Comfyui\ComfyUI'
  if (Test-Path -LiteralPath $desktopComfyUI -PathType Container) {
    $env:COMFYUI_ROOT = $desktopComfyUI
  }
}

if (-not $env:COMFYUI_SHARED_ROOT) {
  $desktopShared = Join-Path $env:LOCALAPPDATA 'Comfy-Desktop\ComfyUI-Shared'
  if (Test-Path -LiteralPath $desktopShared -PathType Container) {
    $env:COMFYUI_SHARED_ROOT = $desktopShared
  }
}

if (-not $env:BLENDER_EXE) {
  $programFiles64 = if ($env:ProgramW6432) { $env:ProgramW6432 } else { $env:ProgramFiles }
  $blenderCandidates = @(
    (Join-Path $programFiles64 'Blender Foundation\Blender 5.2\blender.exe'),
    (Join-Path $programFiles64 'Blender Foundation\Blender 5.1\blender.exe'),
    (Join-Path $programFiles64 'Blender Foundation\Blender 5.0\blender.exe'),
    (Join-Path $env:ProgramFiles 'Blender Foundation\Blender 5.2\blender.exe'),
    (Join-Path $env:ProgramFiles 'Blender Foundation\Blender 5.1\blender.exe'),
    (Join-Path $env:ProgramFiles 'Blender Foundation\Blender 5.0\blender.exe')
  )
  $env:BLENDER_EXE = $blenderCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}

$pythonCommand = Get-Command python -ErrorAction Stop
$pythonExe = $pythonCommand.Source
$runtimeRoot = Join-Path $Root 'runtime\avatar-factory'
$logRoot = Join-Path $runtimeRoot 'logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

function Get-ListeningProcessInfo {
  param([Parameter(Mandatory=$true)][int]$Port)

  $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $connection) { return $null }

  $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction SilentlyContinue
  return [pscustomobject]@{
    Port = $Port
    ProcessId = [int]$connection.OwningProcess
    Name = if ($processInfo) { $processInfo.Name } else { $null }
    ExecutablePath = if ($processInfo) { $processInfo.ExecutablePath } else { $null }
    CommandLine = if ($processInfo) { $processInfo.CommandLine } else { $null }
  }
}

function Wait-PortReleased {
  param(
    [Parameter(Mandatory=$true)][int]$Port,
    [int]$TimeoutSeconds = 10
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) { return }
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $deadline)

  throw "Le port $Port n'a pas été libéré dans le délai imparti."
}

function Stop-OwnedAvatarService {
  param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][int]$Port,
    [Parameter(Mandatory=$true)][string]$ExpectedScript
  )

  $listener = Get-ListeningProcessInfo -Port $Port
  if (-not $listener) { return }

  $scriptName = [System.IO.Path]::GetFileName($ExpectedScript)
  if ([string]::IsNullOrWhiteSpace($listener.CommandLine) -or $listener.CommandLine -notlike "*$scriptName*") {
    throw "$Name ne peut pas être redémarré : le port $Port est occupé par un autre processus (PID $($listener.ProcessId), commande: $($listener.CommandLine))."
  }

  Write-Host "Stopping previous $Name process on port $Port (PID $($listener.ProcessId))..." -ForegroundColor Yellow
  Stop-Process -Id $listener.ProcessId -Force -ErrorAction Stop
  Wait-PortReleased -Port $Port
}

function Read-LogTail {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '' }
  return ((Get-Content -LiteralPath $Path -Tail 40 -ErrorAction SilentlyContinue) -join [Environment]::NewLine)
}

function Wait-ServiceHealth {
  param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][string]$HealthUrl,
    [Parameter(Mandatory=$true)][string]$ExpectedService,
    [Parameter(Mandatory=$true)][System.Diagnostics.Process]$Process,
    [string]$RequiredCapability,
    [object]$RequiredCapabilityValue,
    [Parameter(Mandatory=$true)][string]$ErrorLog
  )

  $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
  $lastError = $null

  do {
    if ($Process.HasExited) {
      $logTail = Read-LogTail -Path $ErrorLog
      throw "$Name s'est arrêté pendant son démarrage (code $($Process.ExitCode)). $logTail"
    }

    try {
      $health = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 3
      if ($health.ok -ne $true) { throw 'Le champ ok n’est pas vrai.' }
      if ([string]$health.service -ne $ExpectedService) {
        throw "Service inattendu : $($health.service)"
      }
      if ($RequiredCapability) {
        $property = $health.PSObject.Properties[$RequiredCapability]
        if (-not $property -or $property.Value -ne $RequiredCapabilityValue) {
          throw "Capacité absente ou invalide : $RequiredCapability"
        }
      }
      return $health
    } catch {
      $lastError = $_.Exception.Message
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)

  $logTail = Read-LogTail -Path $ErrorLog
  throw "$Name n'est pas sain après $StartupTimeoutSeconds secondes. Dernière erreur : $lastError. $logTail"
}

function Start-AvatarService {
  param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][int]$Port,
    [Parameter(Mandatory=$true)][string]$Script,
    [Parameter(Mandatory=$true)][string]$ExpectedService,
    [string]$RequiredCapability,
    [object]$RequiredCapabilityValue
  )

  Stop-OwnedAvatarService -Name $Name -Port $Port -ExpectedScript $Script

  $safeName = ($ExpectedService -replace '[^A-Za-z0-9_-]', '-')
  $stdout = Join-Path $logRoot "$safeName.stdout.log"
  $stderr = Join-Path $logRoot "$safeName.stderr.log"
  Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue

  Write-Host "Starting $Name on http://127.0.0.1:$Port ..." -ForegroundColor Green
  $arguments = "-u `"$Script`""
  $process = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

  $healthParameters = @{
    Name = $Name
    HealthUrl = "http://127.0.0.1:$Port/health"
    ExpectedService = $ExpectedService
    Process = $process
    RequiredCapability = $RequiredCapability
    RequiredCapabilityValue = $RequiredCapabilityValue
    ErrorLog = $stderr
  }
  $health = Wait-ServiceHealth @healthParameters

  Write-Host "$Name healthy (PID $($process.Id))." -ForegroundColor Green
  return [pscustomobject]@{
    name = $Name
    service = $ExpectedService
    port = $Port
    pid = $process.Id
    health = $health
    stdout_log = $stdout
    stderr_log = $stderr
  }
}

Write-Host '=== JS-Innov.IA Avatar Factory ===' -ForegroundColor Cyan
Write-Host "Python: $pythonExe"
python --version

Write-Host 'Checking ComfyUI endpoint...'
try {
  $comfyHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/system_stats' -Method Get -TimeoutSec 5
  Write-Host 'ComfyUI online' -ForegroundColor Green
  $device = @($comfyHealth.devices) | Select-Object -First 1
  if ($device -and [double]$device.vram_free -le 0) {
    Write-Warning 'ComfyUI répond, mais annonce 0 octet de VRAM libre. Vérifiez nvidia-smi avant une génération 3D.'
  }
} catch {
  Write-Warning 'ComfyUI not reachable on 127.0.0.1:8188. Avatar Factory will start, but 3D jobs will fail until ComfyUI is online.'
}

$definitions = @(
  [pscustomobject]@{
    Name = 'Reference upload API'
    Port = 8792
    Script = (Join-Path $PSScriptRoot 'avatar_reference_upload_server.py')
    ExpectedService = 'avatar-reference-upload'
    RequiredCapability = 'generic_manifest_creation'
    RequiredCapabilityValue = $true
  },
  [pscustomobject]@{
    Name = '3D preview API'
    Port = 8793
    Script = (Join-Path $PSScriptRoot 'avatar_preview_server.py')
    ExpectedService = 'avatar-preview'
    RequiredCapability = $null
    RequiredCapabilityValue = $null
  },
  [pscustomobject]@{
    Name = 'Avatar Factory API'
    Port = 8791
    Script = (Join-Path $PSScriptRoot 'avatar_factory_server.py')
    ExpectedService = 'avatar-factory'
    RequiredCapability = $null
    RequiredCapabilityValue = $null
  }
)

$runningServices = @()
try {
  foreach ($definition in $definitions) {
    $startParameters = @{
      Name = $definition.Name
      Port = $definition.Port
      Script = $definition.Script
      ExpectedService = $definition.ExpectedService
      RequiredCapability = $definition.RequiredCapability
      RequiredCapabilityValue = $definition.RequiredCapabilityValue
    }
    $runningServices += Start-AvatarService @startParameters
  }
} catch {
  Write-Error $_
  throw
}

if ($env:COCKPIT_URL -and $env:FINOPS_INGEST_KEY) {
  $finopsScript = Join-Path $PSScriptRoot 'sync_finops.py'
  $existingFinOps = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -like '*sync_finops.py*--watch*'
  }
  foreach ($processInfo in @($existingFinOps)) {
    Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction SilentlyContinue
  }
  $finopsStdout = Join-Path $logRoot 'finops.stdout.log'
  $finopsStderr = Join-Path $logRoot 'finops.stderr.log'
  $finopsArguments = "-u `"$finopsScript`" --watch"
  $finopsProcess = Start-Process -FilePath $pythonExe -ArgumentList $finopsArguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $finopsStdout -RedirectStandardError $finopsStderr
  Write-Host "FinOps synchronization started (PID $($finopsProcess.Id))." -ForegroundColor Green
} else {
  Write-Warning 'FinOps cloud sync disabled until COCKPIT_URL and FINOPS_INGEST_KEY are configured.'
}

$commit = $null
try { $commit = (& git rev-parse HEAD 2>$null).Trim() } catch {}
$state = [ordered]@{
  started_at = (Get-Date).ToUniversalTime().ToString('o')
  repository_root = $Root
  commit = $commit
  services = $runningServices
}
$statePath = Join-Path $runtimeRoot 'services.json'
$state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host ''
Write-Host 'Avatar Factory is ready.' -ForegroundColor Cyan
$runningServices | Select-Object name,service,port,pid | Format-Table -AutoSize
Write-Host "Runtime state: $statePath"
Write-Host "Logs: $logRoot"
