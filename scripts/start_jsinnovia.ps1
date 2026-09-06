param(
  [switch]$InstallStartup,
  [switch]$RemoveStartup,
  [switch]$OpenWeb
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ScriptPath = $PSCommandPath
$Root = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $Root 'runtime\jsinnovia-startup'
$LogPath = Join-Path $RuntimeRoot 'startup.log'
$CockpitUrl = 'https://cockpit.jsinnovia.com'
$BridgeScript = Join-Path $PSScriptRoot 'start_local_ai_bridge.ps1'
$StartupFolder = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
$StartupCmd = Join-Path $StartupFolder 'JS-InnovIA.cmd'

New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null

function Write-StartupLog {
  param(
    [Parameter(Mandatory = $true)][string]$Message,
    [ValidateSet('INFO','OK','WARN','ERROR')][string]$Level = 'INFO'
  )

  $line = '[{0}] [{1}] {2}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $Level, $Message
  Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8

  switch ($Level) {
    'OK'    { Write-Host $Message -ForegroundColor Green }
    'WARN'  { Write-Host $Message -ForegroundColor Yellow }
    'ERROR' { Write-Host $Message -ForegroundColor Red }
    default { Write-Host $Message }
  }
}

function Install-JsInnoviaStartup {
  New-Item -ItemType Directory -Path $StartupFolder -Force | Out-Null
  if ([string]::IsNullOrWhiteSpace($ScriptPath)) {
    throw 'Chemin du script start_jsinnovia.ps1 introuvable.'
  }

  # Ce demarrage ne lance PAS le Cockpit web.
  # Le Cockpit desktop (.exe) conserve son propre demarrage Windows existant.
  $cmd = @(
    '@echo off',
    ('powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $ScriptPath)
  ) -join [Environment]::NewLine

  Set-Content -LiteralPath $StartupCmd -Value $cmd -Encoding ASCII
  Write-StartupLog 'Demarrage automatique IA locale installe pour la session Windows actuelle.' 'OK'
  Write-StartupLog 'Le Cockpit desktop (.exe) n est pas modifie et reste gere par son demarrage Windows existant.' 'INFO'
  Write-StartupLog "Entree de demarrage IA : $StartupCmd" 'INFO'
}

function Remove-JsInnoviaStartup {
  if (Test-Path -LiteralPath $StartupCmd) {
    Remove-Item -LiteralPath $StartupCmd -Force
    Write-StartupLog 'Demarrage automatique IA locale JS-Innov.IA supprime.' 'OK'
  } else {
    Write-StartupLog 'Aucune entree de demarrage automatique IA locale a supprimer.' 'INFO'
  }
}

function Test-OllamaApi {
  try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -Method Get -TimeoutSec 3
    return $true
  } catch {
    return $false
  }
}

function Get-OllamaAllowedModels {
  try {
    $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -Method Get -TimeoutSec 5
    $allowed = @('qwen3.5:4b', 'llama3.2:3b')
    return @($tags.models |
      ForEach-Object { if ($_.name) { $_.name } else { $_.model } } |
      Where-Object { $allowed -contains $_ })
  } catch {
    return @()
  }
}

if ($RemoveStartup) {
  Remove-JsInnoviaStartup
  exit 0
}

if ($InstallStartup) {
  Install-JsInnoviaStartup
}

Write-StartupLog '=== JS-Innov.IA Windows startup ===' 'INFO'

# Recharge la cle depuis le profil utilisateur sans jamais afficher sa valeur.
$userBridgeKey = [Environment]::GetEnvironmentVariable('LOCAL_LLM_BRIDGE_KEY', 'User')
if ([string]::IsNullOrWhiteSpace($userBridgeKey)) {
  Remove-Item Env:LOCAL_LLM_BRIDGE_KEY -ErrorAction SilentlyContinue
  Write-StartupLog 'LOCAL_LLM_BRIDGE_KEY absente du profil utilisateur. Le bridge local ne pourra pas demarrer.' 'WARN'
} else {
  $env:LOCAL_LLM_BRIDGE_KEY = $userBridgeKey.Trim()
  Write-StartupLog ('Cle de jumelage locale chargee ({0} caracteres).' -f $env:LOCAL_LLM_BRIDGE_KEY.Length) 'OK'
}

$env:OLLAMA_URL = 'http://127.0.0.1:11434'
if (-not $env:JSINNOVIA_AGENT_URL) {
  $env:JSINNOVIA_AGENT_URL = 'https://jsinnovia-agent-production.up.railway.app'
}

if (Test-OllamaApi) {
  Write-StartupLog 'Ollama est deja disponible sur 127.0.0.1:11434.' 'OK'
} else {
  Write-StartupLog 'Ollama ne repond pas encore. Demarrage du serveur local...' 'INFO'
  try {
    $ollamaExe = (Get-Command ollama -ErrorAction Stop).Source
    Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
  } catch {
    Write-StartupLog ("Impossible de lancer Ollama : {0}" -f $_.Exception.Message) 'ERROR'
  }

  $ollamaReady = $false
  for ($i = 0; $i -lt 30; $i++) {
    if (Test-OllamaApi) {
      $ollamaReady = $true
      break
    }
    Start-Sleep -Seconds 1
  }

  if ($ollamaReady) {
    Write-StartupLog 'Ollama est maintenant disponible.' 'OK'
  } else {
    Write-StartupLog 'Ollama reste indisponible apres 30 secondes. Les providers cloud restent disponibles.' 'WARN'
  }
}

$models = Get-OllamaAllowedModels
if ($models.Count -gt 0) {
  Write-StartupLog ("Modeles Ollama disponibles : {0}" -f ($models -join ', ')) 'OK'
} else {
  Write-StartupLog 'Aucun modele Ollama autorise detecte (qwen3.5:4b / llama3.2:3b).' 'WARN'
}

$activeBridgeKey = [Environment]::GetEnvironmentVariable('LOCAL_LLM_BRIDGE_KEY', 'Process')
$canStartBridge = (
  -not [string]::IsNullOrWhiteSpace($activeBridgeKey) -and
  $models.Count -gt 0 -and
  (Test-Path -LiteralPath $BridgeScript -PathType Leaf)
)

if ($canStartBridge) {
  try {
    & $BridgeScript
    Write-StartupLog 'Bridge IA local demarre en arriere-plan.' 'OK'
  } catch {
    Write-StartupLog ("Le bridge IA local n'a pas pu demarrer : {0}" -f $_.Exception.Message) 'ERROR'
  }
} else {
  if (-not (Test-Path -LiteralPath $BridgeScript -PathType Leaf)) {
    Write-StartupLog "Script bridge introuvable : $BridgeScript" 'ERROR'
  } else {
    Write-StartupLog 'Bridge IA local non demarre : prerequis manquant.' 'WARN'
  }
}

# Par defaut, ne jamais ouvrir la version web : le Cockpit desktop (.exe) est deja lance par Windows.
# -OpenWeb reste disponible uniquement pour un depannage manuel explicite.
if ($OpenWeb) {
  try {
    Start-Process $CockpitUrl | Out-Null
    Write-StartupLog "Cockpit web ouvert manuellement : $CockpitUrl" 'OK'
  } catch {
    Write-StartupLog ("Impossible d'ouvrir le Cockpit web : {0}" -f $_.Exception.Message) 'ERROR'
  }
} else {
  Write-StartupLog 'Cockpit web non lance. Le Cockpit desktop (.exe) reste prioritaire.' 'OK'
}

Write-StartupLog "Journal : $LogPath" 'INFO'
