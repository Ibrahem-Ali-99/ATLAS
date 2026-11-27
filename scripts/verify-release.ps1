[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

function Invoke-ReleaseStep {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][scriptblock]$Action
  )
  Write-Output "release_step=$Name"
  & $Action
  if ($LASTEXITCODE -ne 0) {
    throw "$Name exited with $LASTEXITCODE"
  }
}

$branch = git rev-parse --abbrev-ref HEAD
if ($LASTEXITCODE -ne 0) { throw "git rev-parse failed" }
if ($branch -ne "feature/atlas-product-completion") {
  throw "Release verification runs on feature/atlas-product-completion. Current branch: $branch"
}

$dirty = git status --porcelain
if ($LASTEXITCODE -ne 0) { throw "git status failed" }
if ($dirty) {
  throw "Working tree is not clean. Finish the other sessions and commit before release verification. This command does not stash, reset, or tag."
}

Write-Output "release_commit=$(git rev-parse HEAD)"

foreach ($path in @(".env", "apps/web/.env.local", "infrastructure/staging/.env", "var")) {
  git check-ignore -q -- $path
  if ($LASTEXITCODE -ne 0) {
    throw "$path is not ignored"
  }
}

$trackedEnv = @(git ls-files | Where-Object { $_ -match '(^|/)\.env($|\.)' -and $_ -notmatch '\.example$' })
if ($trackedEnv.Count -gt 0) {
  throw "Tracked environment files are not examples: $($trackedEnv -join ', ')"
}

Invoke-ReleaseStep "lockfiles" {
  uv lock --check --directory apps/api
  if ($LASTEXITCODE -ne 0) { return }
  npm ci --ignore-scripts --dry-run --prefix apps/web
  if ($LASTEXITCODE -ne 0) { return }
  npm ci --ignore-scripts --dry-run --prefix apps/web-rebuild
}

$headOutput = @(uv run --directory apps/api alembic heads 2>&1)
if ($LASTEXITCODE -ne 0) { throw "alembic heads exited with $LASTEXITCODE" }
$headLines = @($headOutput | Where-Object { "$_" -match '\(head\)' })
if ($headLines.Count -ne 1) {
  throw "Expected one Alembic head. Output: $($headOutput -join ' | ')"
}
Write-Output "release_alembic_head=$($headLines[0])"

Remove-Item Env:ATLAS_LIVE_PROVIDERS -ErrorAction SilentlyContinue
Invoke-ReleaseStep "api" {
  uv run --directory apps/api pytest --tb=line
}

Invoke-ReleaseStep "web-unit" {
  npm run test:unit --prefix apps/web
}
Invoke-ReleaseStep "web-typecheck" {
  Push-Location apps/web
  try { npx tsc --noEmit } finally { Pop-Location }
}
Invoke-ReleaseStep "web-rebuild-typecheck" {
  Push-Location apps/web-rebuild
  try { npx tsc --noEmit } finally { Pop-Location }
}

$env:NEXT_DIST_DIR = ".next-release-check"
try {
  Invoke-ReleaseStep "web-build" {
    Push-Location apps/web
    try { npx next build } finally { Pop-Location }
  }
} finally {
  Remove-Item Env:NEXT_DIST_DIR -ErrorAction SilentlyContinue
}

$env:NEXT_DIST_DIR = ".next-release-check"
try {
  Invoke-ReleaseStep "web-rebuild-build" {
    Push-Location apps/web-rebuild
    try { npx next build } finally { Pop-Location }
  }
} finally {
  Remove-Item Env:NEXT_DIST_DIR -ErrorAction SilentlyContinue
}

foreach ($name in @(
  "ATLAS_E2E_ARTIFACT_DIR",
  "ATLAS_FIGMA_SCREENSHOT_DIR",
  "ATLAS_E2E_PRODUCTION",
  "ATLAS_LIVE_PROVIDERS",
  "NEXT_DIST_DIR"
)) {
  Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $env:LOCALAPPDATA "ms-playwright"
Invoke-ReleaseStep "web-rebuild-browser" {
  Push-Location apps/web-rebuild
  try { npx playwright test --reporter=line } finally { Pop-Location }
}

Write-Output "release_verification=passed"
