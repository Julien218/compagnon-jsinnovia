param(
  [ValidateRange(5, 120)]
  [int]$StartupTimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $env:COMFYUI_ROOT) {
  $candidate = Join-Path $env:LOCALAPPDATA 'Comfy-Desktop\ComfyUI-Installs\Comfyui\ComfyUI'
  if (Test-Path -LiteralPath $candidate -PathType Container) {
    $env:COMFYUI_ROOT = $candidate
  }
}

if (-not $env:COMFYUI_SHARED_ROOT) {
  $candidate = Join-Path $env:LOCALAPPDATA 'Comfy-Desktop\ComfyUI-Shared'
  if (Test-Path -LiteralPath $candidate -PathType Container) {
    $env:COMFYUI_SHARED_ROOT = $candidate
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
  $env:BLENDER_EXE = $blenderCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
}

$pythonExe = (Get-Command python -ErrorAction Stop).Source
$runtimeRoot = Join-Path $Root 'runtime\avatar-factory'
$logRoot = Join-Path $runtimeRoot 'logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

function Get-ListenerInfo {
  param([Parameter(Mandatory = $true)][int]$Port)

  $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if (-not $connection) {
    return $null
  }

  $owner = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $connection.OwningProcess) -ErrorAction SilentlyContinue
  return [pscustomobject]@{
    Port = $Port
    ProcessId = [int]$connection.OwningProcess
    Name = if ($owner) { $owner.Name } else { $null }
    CommandLine = if ($owner) { $owner.CommandLine } else { $null }
  }
}

function Wait-PortFree {
  param(
    [Parameter(Mandatory = $true)][int]$Port,
    [int]$TimeoutSeconds = 10
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $listener) {
      return
    }
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $deadline)

  throw ("Port {0} was not released in time." -f $Port)
}

function Stop-OwnedService {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $true)][string]$ExpectedScript
  )

  $listener = Get-ListenerInfo -Port $Port
  if (-not $listener) {
    return
  }

  $scriptName = [System.IO.Path]::GetFileName($ExpectedScript)
  if ([string]::IsNullOrWhiteSpace($listener.CommandLine) -or $listener.CommandLine -notlike ("*{0}*" -f $scriptName)) {
    throw ("Cannot restart {0}: port {1} belongs to another process. PID={2}; command={3}" -f $Name, $Port, $listener.ProcessId, $listener.CommandLine)
  }

  Write-Host ("Stopping old {0} process on port {1}. PID={2}" -f $Name, $Port, $listener.ProcessId) -ForegroundColor Yellow
  Stop-Process -Id $listener.ProcessId -Force -ErrorAction Stop
  Wait-PortFree -Port $Port
}

function Get-LogTail {
  param([Parameter(Mandatory = $true)][string]$Path)

  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    return ''
  }
  return ((Get-Content -LiteralPath $Path -Tail 40 -ErrorAction SilentlyContinue) -join [Environment]::NewLine)
}

function Wait-Healthy {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$HealthUrl,
    [Parameter(Mandatory = $true)][string]$ExpectedService,
    [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
    [string]$RequiredCapability,
    [object]$RequiredCapabilityValue,
    [Parameter(Mandatory = $true)][string]$ErrorLog
  )

  $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
  $lastError = 'No response received.'

  do {
    $Process.Refresh()
    if ($Process.HasExited) {
      $tail = Get-LogTail -Path $ErrorLog
      throw ("{0} exited during startup. ExitCode={1}. {2}" -f $Name, $Process.ExitCode, $tail)
    }

    try {
      $health = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 3
      if ($health.ok -ne $true) {
        throw 'Health response did not confirm ok=true.'
      }
      if ([string]$health.service -ne $ExpectedService) {
        throw ("Unexpected service: {0}" -f $health.service)
      }
      if ($RequiredCapability) {
        $property = $health.PSObject.Properties[$RequiredCapability]
        if (-not $property -or $property.Value -ne $RequiredCapabilityValue) {
          throw ("Missing or invalid capability: {0}" -f $RequiredCapability)
        }
      }
      return $health
    }
    catch {
      $lastError = $_.Exception.Message
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)

  $tail = Get-LogTail -Path $ErrorLog
  throw ("{0} is not healthy after {1} seconds. LastError={2}. {3}" -f $Name, $StartupTimeoutSeconds, $lastError, $tail)
}

function Start-ManagedService {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $true)][string]$Script,
    [Parameter(Mandatory = $true)][string]$ExpectedService,
    [string]$RequiredCapability,
    [object]$RequiredCapabilityValue
  )

  Stop-OwnedService -Name $Name -Port $Port -ExpectedScript $Script

  $safeName = $ExpectedService -replace '[^A-Za-z0-9_-]', '-'
  $stdout = Join-Path $logRoot ("{0}.stdout.log" -f $safeName)
  $stderr = Join-Path $logRoot ("{0}.stderr.log" -f $safeName)
  Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue

  Write-Host ("Starting {0} on http://127.0.0.1:{1}" -f $Name, $Port) -ForegroundColor Green
  $arguments = '-u "{0}"' -f $Script
  $started = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

  $healthArgs = @{
    Name = $Name
    HealthUrl = ("http://127.0.0.1:{0}/health" -f $Port)
    ExpectedService = $ExpectedService
    Process = $started
    RequiredCapability = $RequiredCapability
    RequiredCapabilityValue = $RequiredCapabilityValue
    ErrorLog = $stderr
  }
  $health = Wait-Healthy @healthArgs

  Write-Host ("{0} healthy. PID={1}" -f $Name, $started.Id) -ForegroundColor Green
  return [pscustomobject]@{
    name = $Name
    service = $ExpectedService
    port = $Port
    pid = $started.Id
    health = $health
    stdout_log = $stdout
    stderr_log = $stderr
  }
}

Write-Host '=== JS-Innov.IA Avatar Factory ===' -ForegroundColor Cyan
Write-Host ("Python: {0}" -f $pythonExe)
python --version

Write-Host 'Checking ComfyUI endpoint...'
try {
  $comfy = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/system_stats' -Method Get -TimeoutSec 5
  Write-Host 'ComfyUI online' -ForegroundColor Green
  $device = @($comfy.devices) | Select-Object -First 1
  if ($device -and [double]$device.vram_free -le 0) {
    Write-Warning 'ComfyUI reports zero free VRAM. Run nvidia-smi before starting a 3D generation.'
  }
}
catch {
  Write-Warning 'ComfyUI is not reachable on 127.0.0.1:8188. The APIs will start, but 3D jobs cannot complete.'
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

$running = @()
foreach ($definition in $definitions) {
  $startArgs = @{
    Name = $definition.Name
    Port = $definition.Port
    Script = $definition.Script
    ExpectedService = $definition.ExpectedService
    RequiredCapability = $definition.RequiredCapability
    RequiredCapabilityValue = $definition.RequiredCapabilityValue
  }
  $running += Start-ManagedService @startArgs
}

if ($env:COCKPIT_URL -and $env:FINOPS_INGEST_KEY) {
  $finopsScript = Join-Path $PSScriptRoot 'sync_finops.py'
  $existingWatchers = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*sync_finops.py*--watch*' }
  foreach ($watcher in @($existingWatchers)) {
    Stop-Process -Id $watcher.ProcessId -Force -ErrorAction SilentlyContinue
  }

  $finopsOut = Join-Path $logRoot 'finops.stdout.log'
  $finopsErr = Join-Path $logRoot 'finops.stderr.log'
  Remove-Item -LiteralPath $finopsOut, $finopsErr -Force -ErrorAction SilentlyContinue
  $finopsArguments = '-u "{0}" --watch' -f $finopsScript
  $finopsProcess = Start-Process -FilePath $pythonExe -ArgumentList $finopsArguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $finopsOut -RedirectStandardError $finopsErr
  Write-Host ("FinOps synchronization started. PID={0}" -f $finopsProcess.Id) -ForegroundColor Green
}
else {
  Write-Warning 'FinOps cloud sync is disabled until COCKPIT_URL and FINOPS_INGEST_KEY are configured.'
}

$commit = $null
try {
  $commit = (& git rev-parse HEAD 2>$null).Trim()
}
catch {
  $commit = $null
}

$state = [ordered]@{
  started_at = (Get-Date).ToUniversalTime().ToString('o')
  repository_root = $Root
  commit = $commit
  services = $running
}
$statePath = Join-Path $runtimeRoot 'services.json'
$state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host ''
Write-Host 'Avatar Factory is ready.' -ForegroundColor Cyan
$running | Select-Object name, service, port, pid | Format-Table -AutoSize
Write-Host ("Runtime state: {0}" -f $statePath)
Write-Host ("Logs: {0}" -f $logRoot)
