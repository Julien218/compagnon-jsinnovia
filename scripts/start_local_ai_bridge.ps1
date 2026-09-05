param(
  [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $Root 'runtime\local-ai-bridge'
$LogRoot = Join-Path $RuntimeRoot 'logs'
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

if (-not $env:LOCAL_LLM_BRIDGE_KEY) {
  throw 'LOCAL_LLM_BRIDGE_KEY n''est pas configurée. Le jumelage Railway doit être effectué avant le démarrage.'
}

if (-not $env:JSINNOVIA_AGENT_URL) {
  $env:JSINNOVIA_AGENT_URL = 'https://jsinnovia-agent-production.up.railway.app'
}
if (-not $env:OLLAMA_URL) {
  $env:OLLAMA_URL = 'http://127.0.0.1:11434'
}

Write-Host '=== JS-Innov.IA Local AI Bridge ===' -ForegroundColor Cyan
Write-Host 'Vérification Ollama...'
$tags = Invoke-RestMethod -Uri "$($env:OLLAMA_URL)/api/tags" -Method Get -TimeoutSec 5
$models = @($tags.models | ForEach-Object { if ($_.name) { $_.name } else { $_.model } })
$allowed = @('qwen3.5:4b', 'llama3.2:3b')
$available = @($models | Where-Object { $allowed -contains $_ })
if ($available.Count -eq 0) {
  throw 'Aucun modèle Ollama autorisé trouvé. Attendus: qwen3.5:4b ou llama3.2:3b.'
}
Write-Host ("Ollama OK : {0}" -f ($available -join ', ')) -ForegroundColor Green

$workerScript = Join-Path $PSScriptRoot 'ollama_bridge_worker.py'
if (-not (Test-Path -LiteralPath $workerScript -PathType Leaf)) {
  throw "Worker introuvable: $workerScript"
}
$pythonExe = (Get-Command python -ErrorAction Stop).Source

$existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -and $_.CommandLine -like '*ollama_bridge_worker.py*' }
foreach ($process in @($existing)) {
  Write-Host ("Arrêt de l'ancien bridge PID={0}" -f $process.ProcessId) -ForegroundColor Yellow
  Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

if ($Foreground) {
  & $pythonExe -u $workerScript
  exit $LASTEXITCODE
}

$stdout = Join-Path $LogRoot 'bridge.stdout.log'
$stderr = Join-Path $LogRoot 'bridge.stderr.log'
Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
$arguments = '-u "{0}"' -f $workerScript
$process = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Start-Sleep -Seconds 3
$process.Refresh()
if ($process.HasExited) {
  $tail = if (Test-Path -LiteralPath $stderr) { (Get-Content -LiteralPath $stderr -Tail 30) -join [Environment]::NewLine } else { '' }
  throw "Le bridge s'est arrêté au démarrage. $tail"
}

$state = [ordered]@{
  started_at = (Get-Date).ToUniversalTime().ToString('o')
  pid = $process.Id
  ollama_url = $env:OLLAMA_URL
  cloud_url = $env:JSINNOVIA_AGENT_URL
  models = $available
  stdout_log = $stdout
  stderr_log = $stderr
}
$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $RuntimeRoot 'bridge.json') -Encoding UTF8

Write-Host ("Bridge local démarré. PID={0}" -f $process.Id) -ForegroundColor Green
Write-Host 'Ollama reste uniquement accessible sur 127.0.0.1:11434.' -ForegroundColor Green
Write-Host ("Logs: {0}" -f $LogRoot)
