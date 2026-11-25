Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Run this only from an authorized Windows checkout with the disposable ATLAS
# PostgreSQL container published on 127.0.0.1:5434. It never targets the
# development/staging database name `atlas`.
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$api = Join-Path $repo "apps\api"
$web = Join-Path $repo "apps\web"
$python = Join-Path $api ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "ATLAS API virtualenv not found: $python" }

. (Join-Path $PSScriptRoot "e2e-config.ps1")
Set-AtlasE2EEnvironment

Write-Output "E2E target database=atlas_e2e api_port=$($env:ATLAS_E2E_API_PORT) web_port=$($env:ATLAS_E2E_WEB_PORT) api_url=$($env:NEXT_PUBLIC_API_URL)"

$probe = Test-NetConnection -ComputerName 127.0.0.1 -Port 5434 -InformationLevel Quiet
if (-not $probe) { throw "PostgreSQL is not reachable at 127.0.0.1:5434" }

Push-Location $api
try {
  # Creates/migrates only atlas_e2e and prepares its disposable fixture.
  & $python -m app.scripts.e2e_database
  if ($LASTEXITCODE -ne 0) { throw "Disposable atlas_e2e migration/setup failed with exit $LASTEXITCODE" }

  # The pytest harness creates and truncates only atlas_test and
  # atlas_migration_test; both are disposable test databases.
  & $python -m pytest -q tests/test_invitations.py tests/test_auth.py tests/test_authorization.py tests/test_knowledge_jobs.py tests/test_knowledge.py tests/test_retrieval.py tests/test_crm.py tests/test_automation.py tests/test_approvals.py tests/test_email_delivery.py tests/test_email_delivery_policy.py tests/test_webchat_handoff.py
  if ($LASTEXITCODE -ne 0) { throw "Identity or durable-ingestion tests failed with exit $LASTEXITCODE" }

  # The Playwright harness prepares only the same disposable databases, starts
  # an isolated API/Mailpit pair, and tears both down through its own hooks.
  Push-Location $web
  try {
    $env:ATLAS_E2E_SKIP_MAILPIT = "0"
    Write-Output "Running authentication preflight and CRM scenario in one browser session"
    & npx playwright test e2e/auth-preflight.spec.ts e2e/crm-acceptance.spec.ts
    if ($LASTEXITCODE -ne 0) { throw "Authentication preflight or CRM browser acceptance failed with exit $LASTEXITCODE" }
    Write-Output "Authentication preflight and CRM scenario passed"
    & npx playwright test e2e/workspace.spec.ts e2e/knowledge-acceptance.spec.ts e2e/crm-acceptance.spec.ts e2e/crm-follow-up-acceptance.spec.ts e2e/overview-analytics-acceptance.spec.ts
    if ($LASTEXITCODE -ne 0) { throw "MVP browser acceptance failed with exit $LASTEXITCODE" }
  }
  finally {
    Pop-Location
  }
}
finally {
  Pop-Location
}

Write-Output "ATLAS MVP verification passed against disposable databases."
