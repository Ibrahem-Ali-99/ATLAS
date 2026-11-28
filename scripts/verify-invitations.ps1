Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Run this only from an authorized Windows checkout with the disposable ATLAS
# PostgreSQL container published on 127.0.0.1:5434. It never targets the
# development/staging database name `atlas`.
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$api = Join-Path $repo "apps\api"
$web = Join-Path $repo "apps\web-rebuild"
$python = Join-Path $api ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "ATLAS API virtualenv not found: $python" }
$state = Join-Path $repo "var\dev"
New-Item -ItemType Directory -Force -Path $state | Out-Null
. (Join-Path $PSScriptRoot "native-command.ps1")

. (Join-Path $PSScriptRoot "e2e-config.ps1")
Set-AtlasE2EEnvironment

Write-Output "E2E target database=per-run api_port=$($env:ATLAS_E2E_API_PORT) web_port=$($env:ATLAS_E2E_WEB_PORT) api_url=$($env:ATLAS_API_URL)"

$probe = Test-NetConnection -ComputerName 127.0.0.1 -Port 5434 -InformationLevel Quiet
if (-not $probe) { throw "PostgreSQL is not reachable at 127.0.0.1:5434" }

Push-Location $api
try {
  # The pytest harness creates and truncates only atlas_test and
  # atlas_migration_test; both are disposable test databases.
  Invoke-AtlasNative -FilePath $python -ArgumentList @("-m", "pytest", "-q", "tests/test_invitations.py", "tests/test_auth.py", "tests/test_authorization.py", "tests/test_knowledge_jobs.py", "tests/test_knowledge.py", "tests/test_retrieval.py", "tests/test_crm.py", "tests/test_automation.py", "tests/test_approvals.py", "tests/test_email_delivery.py", "tests/test_email_delivery_policy.py", "tests/test_webchat_handoff.py") -LogPath (Join-Path $state "focused-api-tests.log") | Out-Null

  # The Playwright harness prepares only the same disposable databases, starts
  # an isolated API/Mailpit pair, and tears both down through its own hooks.
  Push-Location $web
  try {
    $env:ATLAS_E2E_SKIP_MAILPIT = "0"
    Write-Output "Running authentication preflight and CRM scenario in one browser session"
    Invoke-AtlasNative -FilePath "npx" -ArgumentList @("playwright", "test", "e2e/auth-preflight.spec.ts", "e2e/crm-acceptance.spec.ts") -LogPath (Join-Path $state "auth-crm-browser-tests.log") | Out-Null
    Write-Output "Authentication preflight and CRM scenario passed"
    Invoke-AtlasNative -FilePath "npx" -ArgumentList @("playwright", "test", "e2e/workspace.spec.ts", "e2e/knowledge-acceptance.spec.ts", "e2e/crm-acceptance.spec.ts", "e2e/crm-follow-up-acceptance.spec.ts", "e2e/overview-analytics-acceptance.spec.ts", "e2e/automations-integrations-acceptance.spec.ts") -LogPath (Join-Path $state "mvp-browser-tests.log") | Out-Null
  }
  finally {
    Pop-Location
  }
}
finally {
  Pop-Location
}

Write-Output "ATLAS MVP verification passed against disposable databases."
