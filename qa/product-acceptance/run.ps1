$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root
& (Join-Path $Root "apps\api\.venv\Scripts\python.exe") (Join-Path $PSScriptRoot "harness\launch.py")
exit $LASTEXITCODE
