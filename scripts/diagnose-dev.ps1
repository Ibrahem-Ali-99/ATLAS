Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$state = Join-Path $repo "var\dev"
New-Item -ItemType Directory -Force -Path $state | Out-Null
. (Join-Path $PSScriptRoot "native-command.ps1")
$report = Join-Path $state "diagnostics.txt"

function Port([int]$Number) {
  $listeners = Get-NetTCPConnection -LocalPort $Number -State Listen -ErrorAction SilentlyContinue
  if (-not $listeners) { return "$Number=not-listening" }
  $owners = $listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
    $p = Get-Process -Id $_ -ErrorAction SilentlyContinue
    if ($p) { "$($p.ProcessName)[$_]" } else { "pid[$_]" }
  }
  return "$Number=listening:$($owners -join ',')"
}

$lines = @()
$lines += "timestamp=$((Get-Date).ToString('o'))"
$lines += "repo=$repo"
$lines += "branch=$((git -C $repo branch --show-current 2>$null))"
$lines += "commit=$((git -C $repo rev-parse HEAD 2>$null))"
$lines += (Port 3000); $lines += (Port 3011); $lines += (Port 8000); $lines += (Port 8011); $lines += (Port 5434)
$lines += "--- docker info ---"
$dockerInfoLog = Join-Path $state "diagnostic-docker-info.log"
Invoke-AtlasNative -FilePath "docker" -ArgumentList @("info") -LogPath $dockerInfoLog -AllowFailure | Out-Null
$lines += (Get-Content -LiteralPath $dockerInfoLog | Select-Object -Last 8)
$lines += "--- compose ps ---"
$composeLog = Join-Path $state "diagnostic-compose-ps.log"
Invoke-AtlasNative -FilePath "docker" -ArgumentList @("compose", "-f", (Join-Path $repo 'compose.yaml'), "ps") -LogPath $composeLog -AllowFailure | Out-Null
$lines += Get-Content -LiteralPath $composeLog
foreach ($url in @("http://127.0.0.1:8000/api/v1/health", "http://127.0.0.1:8000/api/v1/ready", "http://127.0.0.1:3011/login", "http://127.0.0.1:3000/login")) {
  try {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 4
    $lines += "$url status=$($response.StatusCode)"
  } catch {
    $lines += "$url unavailable=$($_.Exception.GetType().Name)"
  }
}
$lines | Out-File -LiteralPath $report -Encoding utf8
Get-Content -LiteralPath $report
Write-Output "Redacted diagnostics written to $report"
