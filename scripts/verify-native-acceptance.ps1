[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$PostgresBin,
  [ValidateSet("All", "Api", "Browser")][string]$Mode = "All",
  [string]$BrowserCache,
  [switch]$RestoreCheck,
  [string[]]$ApiTests = @(),
  [string[]]$BrowserSpecs = @(
    "e2e/auth-preflight.spec.ts", "e2e/automations-integrations-acceptance.spec.ts",
    "e2e/campaign-acceptance.spec.ts",
    "e2e/crm-acceptance.spec.ts", "e2e/crm-follow-up-acceptance.spec.ts",
    "e2e/inbox-acceptance.spec.ts", "e2e/knowledge-acceptance.spec.ts", "e2e/overview-analytics-acceptance.spec.ts",
    "e2e/setup-acceptance.spec.ts", "e2e/workflow-acceptance.spec.ts", "e2e/workspace.spec.ts"
  )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-LoopbackPort {
  $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
  try {
    $listener.Start()
    return $listener.LocalEndpoint.Port
  } finally {
    $listener.Stop()
  }
}

. (Join-Path $PSScriptRoot "native-command.ps1")
. (Join-Path $PSScriptRoot "e2e-config.ps1")
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bin = (Resolve-Path -LiteralPath $PostgresBin).Path
$run = Join-Path $repo ("var\native-acceptance-" + [guid]::NewGuid().ToString("N"))
$cluster = Join-Path $run "postgres"
$passwordFile = Join-Path $run "init-password"
$python = Join-Path $repo "apps\api\.venv\Scripts\python.exe"
$envKeys = @(
  "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD", "PGPASSWORD",
  "SEED_ADMIN_EMAIL", "SEED_ADMIN_PASSWORD", "SEED_ADMIN_NAME", "SEED_STAFF_EMAIL",
  "SEED_STAFF_PASSWORD", "SEED_STAFF_NAME", "SEED_OUTSIDER_EMAIL", "SEED_OUTSIDER_PASSWORD",
  "SEED_OUTSIDER_NAME", "ATLAS_STORAGE_DIR", "ATLAS_MODEL_DIR", "NEXT_DIST_DIR",
  "ATLAS_E2E_POSTGRES_HOST", "ATLAS_E2E_PRODUCTION", "ATLAS_E2E_API_PORT", "ATLAS_E2E_WEB_PORT",
  "ATLAS_E2E_EXTERNAL_WEB",
  "ATLAS_API_URL", "ATLAS_E2E_SKIP_MAILPIT", "ATLAS_E2E_ARTIFACT_DIR", "PLAYWRIGHT_BROWSERS_PATH"
)
$previousEnv = @{}
foreach ($key in $envKeys) { $previousEnv[$key] = [Environment]::GetEnvironmentVariable($key) }
New-Item -ItemType Directory -Path $run | Out-Null
$env:POSTGRES_PASSWORD = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
$env:POSTGRES_USER = "atlas"
$env:ATLAS_STORAGE_DIR = Join-Path $run "uploads"
$env:ATLAS_MODEL_DIR = Join-Path $run "models"
Set-AtlasE2EEnvironment
$env:POSTGRES_PORT = [string](Get-LoopbackPort)
$server = $null
$webServer = $null

try {
  Set-Content -LiteralPath $passwordFile -Value $env:POSTGRES_PASSWORD -Encoding ascii
  try {
    Invoke-AtlasNative -FilePath "$bin\initdb.exe" -ArgumentList @(
      "-D", $cluster, "-U", $env:POSTGRES_USER, "--auth=scram-sha-256", "--pwfile=$passwordFile",
      "--encoding=UTF8", "--locale=C"
    ) -LogPath (Join-Path $run "initdb.log") | Out-Null
  } finally {
    Remove-Item -LiteralPath $passwordFile
  }
  $server = Start-Process -FilePath "$bin\postgres.exe" -ArgumentList @(
    "-D", ('"{0}"' -f $cluster), "-h", "127.0.0.1", "-p", $env:POSTGRES_PORT
  ) -RedirectStandardOutput (Join-Path $run "postgres.stdout.log") `
    -RedirectStandardError (Join-Path $run "postgres.stderr.log") -WindowStyle Hidden -PassThru
  $ready = $false
  for ($attempt = 0; $attempt -lt 20 -and !$server.HasExited; $attempt++) {
    & "$bin\pg_isready.exe" -q -h 127.0.0.1 -p $env:POSTGRES_PORT -t 1
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Milliseconds 500
  }
  if (!$ready -or $server.HasExited) { throw "The disposable PostgreSQL instance did not start. See $run" }
  if ($Mode -ne "Browser") {
    Push-Location (Join-Path $repo "apps\api")
    try {
      Invoke-AtlasNative -FilePath $python -ArgumentList (@(
        "-m", "pytest", "-o", "addopts=", "-q", "-ra", "--tb=short", "--basetemp", (Join-Path $run "pytest")
      ) + $ApiTests) -LogPath (Join-Path $run "api.log") | Out-Null
    } finally { Pop-Location }
  }
  if ($Mode -ne "Api") {
    $env:ATLAS_E2E_WEB_PORT = [string](Get-LoopbackPort)
    do { $env:ATLAS_E2E_API_PORT = [string](Get-LoopbackPort) } while ($env:ATLAS_E2E_API_PORT -eq $env:ATLAS_E2E_WEB_PORT)
    $env:ATLAS_API_URL = "http://127.0.0.1:$($env:ATLAS_E2E_API_PORT)"
    $env:NEXT_DIST_DIR = ".next-e2e-phase2d"
    $env:ATLAS_E2E_SKIP_MAILPIT = "1"
    $env:ATLAS_E2E_ARTIFACT_DIR = Join-Path $run "screenshots"
    $env:ATLAS_E2E_EXTERNAL_WEB = "1"
    if ($BrowserCache) { $env:PLAYWRIGHT_BROWSERS_PATH = (Resolve-Path -LiteralPath $BrowserCache).Path }
    Push-Location (Join-Path $repo "apps\web-rebuild")
    try {
      Invoke-AtlasNative -FilePath "node" -ArgumentList @(
        "node_modules/next/dist/bin/next", "build"
      ) -LogPath (Join-Path $run "web-build.log") | Out-Null
      $webServer = Start-Process -FilePath "node" -ArgumentList @(
        "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", $env:ATLAS_E2E_WEB_PORT
      ) -WorkingDirectory (Get-Location).Path -RedirectStandardOutput (Join-Path $run "web.stdout.log") `
        -RedirectStandardError (Join-Path $run "web.stderr.log") -WindowStyle Hidden -PassThru
      $webReady = $false
      for ($attempt = 0; $attempt -lt 30 -and !$webServer.HasExited; $attempt++) {
        try {
          $response = Invoke-WebRequest "http://127.0.0.1:$($env:ATLAS_E2E_WEB_PORT)/login" -TimeoutSec 2
          if ($response.StatusCode -eq 200) { $webReady = $true; break }
        } catch {
          Start-Sleep -Milliseconds 500
        }
      }
      if (!$webReady) { throw "The disposable frontend did not start. See $run" }
      Invoke-AtlasNative -FilePath "node" -ArgumentList (
        @("node_modules/playwright/cli.js", "test", "--output", (Join-Path $run "browser-results")) + $BrowserSpecs
      ) -LogPath (Join-Path $run "browser.log") | Out-Null
    } finally { Pop-Location }
  }
  if ($RestoreCheck) {
    $env:PGPASSWORD = $env:POSTGRES_PASSWORD
    $connection = @("-h", "127.0.0.1", "-p", $env:POSTGRES_PORT, "-U", $env:POSTGRES_USER)
    $sourceDatabase = "atlas_test"
    if ($Mode -ne "Api") {
      $sourceDatabase = & "$bin\psql.exe" @connection -d postgres -At -v ON_ERROR_STOP=1 -c `
        "SELECT datname FROM pg_database WHERE datname ~ '^atlas_e2e_[0-9a-f]{32}$' LIMIT 1"
      if ($LASTEXITCODE -ne 0 -or $sourceDatabase -notmatch '^atlas_e2e_[0-9a-f]{32}$') {
        throw "Could not identify the disposable browser database for restore verification"
      }
    }
    $archive = Join-Path $run "restore-check.dump"
    Invoke-AtlasNative -FilePath "$bin\pg_dump.exe" -ArgumentList ($connection + @(
      "-d", $sourceDatabase, "-Fc", "-f", $archive
    )) -LogPath (Join-Path $run "dump.log") | Out-Null
    Invoke-AtlasNative -FilePath "$bin\createdb.exe" -ArgumentList ($connection + @(
      "atlas_restore_check"
    )) -LogPath (Join-Path $run "create-restore-target.log") | Out-Null
    Invoke-AtlasNative -FilePath "$bin\pg_restore.exe" -ArgumentList ($connection + @(
      "-d", "atlas_restore_check", "--exit-on-error", $archive
    )) -LogPath (Join-Path $run "restore.log") | Out-Null
    $fingerprint = "SELECT version_num, (SELECT count(*) FROM organizations), (SELECT count(*) FROM leads), (SELECT count(*) FROM documents) FROM alembic_version"
    $before = & "$bin\psql.exe" @connection -d $sourceDatabase -At -v ON_ERROR_STOP=1 -c $fingerprint
    if ($LASTEXITCODE -ne 0) { throw "Source database verification failed" }
    $after = & "$bin\psql.exe" @connection -d atlas_restore_check -At -v ON_ERROR_STOP=1 -c $fingerprint
    if ($LASTEXITCODE -ne 0 -or !$before -or $before -ne $after) { throw "Restored database verification failed" }
    "Migration and row counts (organizations, leads, documents): $after" | Set-Content (Join-Path $run "restore-verification.log")
    if ($Mode -ne "Api") {
      $uploadRoot = Join-Path $repo "var\$sourceDatabase\uploads"
      $uploadArchive = Join-Path $run "restore-uploads.tar"
      $restoredUploads = Join-Path $run "restored-uploads"
      $checkedFiles = 0
      if (Test-Path -LiteralPath $uploadRoot -PathType Container) {
        $sourceRoot = (Resolve-Path -LiteralPath $uploadRoot).Path
        $sourcePrefix = $sourceRoot.TrimEnd('\') + '\'
        New-Item -ItemType Directory -Path $restoredUploads | Out-Null
        Invoke-AtlasNative -FilePath "tar.exe" -ArgumentList @(
          "-cf", $uploadArchive, "-C", $sourceRoot, "."
        ) -LogPath (Join-Path $run "upload-archive.log") | Out-Null
        Invoke-AtlasNative -FilePath "tar.exe" -ArgumentList @(
          "-xf", $uploadArchive, "-C", $restoredUploads
        ) -LogPath (Join-Path $run "upload-restore.log") | Out-Null
        $documents = & "$bin\psql.exe" @connection -d atlas_restore_check -At -v ON_ERROR_STOP=1 -c `
          "SELECT storage_path, byte_size FROM documents WHERE storage_path <> ''"
        if ($LASTEXITCODE -ne 0) { throw "Could not read the restored document references" }
        foreach ($document in $documents) {
          $storedPath, $size = $document -split '\|', 2
          if (!$storedPath.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) { continue }
          $relativePath = $storedPath.Substring($sourcePrefix.Length)
          if ($relativePath -notmatch '^[0-9a-f-]{36}[\\/][0-9a-f-]{36}$') {
            throw "The restored database referenced an unexpected upload path"
          }
          $restoredPath = Join-Path $restoredUploads $relativePath
          if ((Get-Item -LiteralPath $restoredPath).Length -ne [long]$size -or
              (Get-FileHash -LiteralPath $storedPath).Hash -ne (Get-FileHash -LiteralPath $restoredPath).Hash) {
            throw "A restored upload differs from its source"
          }
          $checkedFiles++
        }
      }
      "Restored database references with matching uploaded file sizes and SHA-256: $checkedFiles" |
        Add-Content (Join-Path $run "restore-verification.log")
    }
  }
} finally {
  if ($null -ne $webServer -and !$webServer.HasExited) {
    $webServer.Kill()
    $null = $webServer.WaitForExit(5000)
  }
  if ($null -ne $server -and !$server.HasExited) {
    & "$bin\pg_ctl.exe" -D $cluster stop -m fast -W
  }
  foreach ($key in $envKeys) { [Environment]::SetEnvironmentVariable($key, $previousEnv[$key]) }
  Write-Output "Acceptance evidence: $run"
}
