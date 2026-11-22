# Run the same quality checks CI runs. Secret scanning uses Docker when the image is available.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    Write-Host ""
    Write-Host "== $Label =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Push-Location (Join-Path $Root "apps\api")
Invoke-Checked "ruff check" { uv run ruff check app tests }
Invoke-Checked "ruff format" { uv run ruff format --check app tests }
Invoke-Checked "mypy" { uv run mypy }
Invoke-Checked "pytest" { uv run pytest }
Pop-Location

Push-Location (Join-Path $Root "apps\web")
Invoke-Checked "eslint" { npm run lint }
Invoke-Checked "next build" { npm run build }
Invoke-Checked "tsc" { npm run typecheck }
Pop-Location

# Git history mode skips ignored files such as .env. A filesystem scan would also read .venv and .next.
$gitleaksConfig = Join-Path $Root ".gitleaks.toml"
$gitleaks = Get-Command gitleaks -ErrorAction SilentlyContinue
if ($gitleaks) {
    Invoke-Checked "gitleaks" {
        gitleaks detect --source $Root --redact --config $gitleaksConfig
    }
} else {
    $mount = $Root.Path.Replace("\", "/")
    Invoke-Checked "gitleaks (docker)" {
        docker run --rm -v "${mount}:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 detect --source /repo --redact --config /repo/.gitleaks.toml
    }
}

Write-Host ""
Write-Host "Quality checks passed."
