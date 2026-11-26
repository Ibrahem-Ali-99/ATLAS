param(
  [switch]$WithN8n,
  [switch]$SkipSeed,
  [switch]$NoNewWindows
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$api = Join-Path $repo "apps\api"
$web = Join-Path $repo "apps\web"
$state = Join-Path $repo "var\dev"
New-Item -ItemType Directory -Force -Path $state | Out-Null
. (Join-Path $PSScriptRoot "native-command.ps1")

function Require-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command '$Name' was not found on PATH."
  }
}

function Read-DotEnv([string]$Path) {
  $values = @{}
  if (-not (Test-Path -LiteralPath $Path)) { return $values }
  foreach ($line in Get-Content -LiteralPath $Path) {
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)\s*$') {
      $values[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
    }
  }
  return $values
}

function Test-Port([int]$Port) {
  return [bool](Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue)
}

function Show-PortOwner([int]$Port) {
  $owners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
  if (-not $owners) { return "none" }
  return (($owners | ForEach-Object {
    $process = Get-Process -Id $_ -ErrorAction SilentlyContinue
    if ($process) { "$($process.ProcessName)[$_]" } else { "pid[$_]" }
  }) -join ", ")
}

function Describe-PortConflict([int]$Port) {
  $owner = Show-PortOwner $Port
  $containers = @()
  try {
    $containers = @(docker ps --format '{{.Names}}|{{.Ports}}' 2>$null | Where-Object { $_ -match "(^|[,:])$Port->" -or $_ -match "->$Port/" })
  } catch { }
  if ($containers.Count -gt 0) {
    return "port $Port is occupied by $owner; Docker container mapping: $($containers -join ', '). If this is the ATLAS API container, stop it explicitly with 'docker stop <container-name>' or 'docker compose stop api', then rerun this launcher. No container was stopped automatically."
  }
  return "port $Port is occupied by $owner. Identify the intended process, stop it explicitly, then rerun this launcher. No process was terminated automatically."
}

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 60) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
    } catch { }
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)
  return $false
}

Require-Command "docker"
Require-Command "uv"
Require-Command "npm"
if (-not (Test-Path -LiteralPath (Join-Path $repo ".env"))) {
  throw "Missing .env. Copy .env.example to .env and set a non-placeholder ATLAS_SECRET_KEY."
}

$envValues = Read-DotEnv (Join-Path $repo ".env")
$required = @("ATLAS_SECRET_KEY", "ATLAS_DATABASE_URL", "POSTGRES_PORT")
foreach ($name in $required) {
  if (-not $envValues.ContainsKey($name) -or [string]::IsNullOrWhiteSpace($envValues[$name])) {
    throw "Missing required local configuration: $name"
  }
}
if ($envValues["POSTGRES_PORT"] -ne "5434") {
  throw "Normal development requires POSTGRES_PORT=5434. Change only the local .env value if the port is intentionally different."
}
if ($envValues["ATLAS_DATABASE_URL"] -notmatch ':(5434)(/|$)') {
  throw "Normal development requires ATLAS_DATABASE_URL to target host port 5434."
}
if ($envValues["ATLAS_SECRET_KEY"] -match '(?i)(replace-with|change-me|changeme|dev-only)' -or $envValues["ATLAS_SECRET_KEY"].Length -lt 32) {
  throw "ATLAS_SECRET_KEY must be a non-placeholder value of at least 32 characters."
}

foreach ($port in @(3000, 8000)) {
  if (Test-Port $port) {
    throw (Describe-PortConflict $port)
  }
}

Invoke-AtlasNative -FilePath "docker" -ArgumentList @("info") -LogPath (Join-Path $state "docker-info.log") | Out-Null

Write-Output "Starting normal infrastructure on PostgreSQL host port 5434..."
$services = @("postgres", "mailpit")
if ($WithN8n) { $services += "n8n" }
Invoke-AtlasNative -FilePath "docker" -ArgumentList (@("compose", "up", "-d") + $services) -LogPath (Join-Path $state "compose-up.log") | Out-Null

Write-Output "Waiting for PostgreSQL and API dependencies..."
$pgReady = $false
for ($i = 0; $i -lt 30; $i++) {
  $readyCode = Invoke-AtlasNative -FilePath "docker" -ArgumentList @("compose", "exec", "-T", "postgres", "pg_isready", "-U", $envValues["POSTGRES_USER"], "-d", $envValues["POSTGRES_DB"]) -LogPath (Join-Path $state "postgres-ready.log") -AllowFailure
  if ($readyCode -eq 0) { $pgReady = $true; break }
  Start-Sleep -Seconds 2
}
if (-not $pgReady) { throw "PostgreSQL did not become ready. See var/dev/postgres-ready.log." }

Push-Location $api
try {
  Invoke-AtlasNative -FilePath "uv" -ArgumentList @("run", "alembic", "upgrade", "head") -LogPath (Join-Path $state "migrations.log") | Out-Null
  if (-not $SkipSeed) {
    Invoke-AtlasNative -FilePath "uv" -ArgumentList @("run", "python", "-m", "app.scripts.seed") -LogPath (Join-Path $state "seed.log") | Out-Null
  }
} finally { Pop-Location }

$apiCommand = "Set-Location '$api'; uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log 2>&1 | Tee-Object '$state\api.log'"
$webCommand = "Set-Location '$web'; `$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8000'; npm run dev -- --hostname 127.0.0.1 --port 3000 2>&1 | Tee-Object '$state\web.log'"
if ($NoNewWindows) {
  Write-Output "Start API: $apiCommand"
  Write-Output "Start web: $webCommand"
} else {
  Start-Process powershell.exe -ArgumentList @("-NoExit", "-Command", $apiCommand) -WorkingDirectory $repo
  if (-not (Wait-Http "http://127.0.0.1:8000/api/v1/health" 60)) { throw "API did not become reachable. See var/dev/api.log." }
  Start-Process powershell.exe -ArgumentList @("-NoExit", "-Command", $webCommand) -WorkingDirectory $repo
}

Write-Output "Normal ATLAS development target: http://127.0.0.1:3000"
Write-Output "API readiness: http://127.0.0.1:8000/api/v1/ready"
Write-Output "Diagnostics: $state"
Write-Output "Shutdown: .\scripts\stop-dev.ps1"
