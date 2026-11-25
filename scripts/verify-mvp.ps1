Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Single local MVP verification entry point. The delegated script refuses the
# development/staging database names and owns only its disposable E2E services.
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$delegate = Join-Path $repo "scripts\verify-invitations.ps1"
if (-not (Test-Path -LiteralPath $delegate)) { throw "Missing verification script: $delegate" }
. (Join-Path $PSScriptRoot "e2e-config.ps1")
Set-AtlasE2EEnvironment

& $delegate
if ($LASTEXITCODE -ne 0) {
  throw "ATLAS MVP verification failed with exit $LASTEXITCODE"
}

Write-Output "ATLAS MVP verification completed successfully."
