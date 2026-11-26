Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "native-command.ps1")

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$testDir = Join-Path $root "var\dev-native-tests"
New-Item -ItemType Directory -Force -Path $testDir | Out-Null

function Assert([bool]$Condition, [string]$Message) {
  if (-not $Condition) { throw $Message }
}

$mixedLog = Join-Path $testDir "mixed.log"
$mixedCode = Invoke-AtlasNative -FilePath "cmd.exe" -ArgumentList @("/c", "echo stdout-line&echo stderr-line 1>&2") -LogPath $mixedLog
Assert ($mixedCode -eq 0) "A successful command with stderr must return zero."
$mixedText = Get-Content -Raw $mixedLog
Assert ($mixedText.Contains("stdout-line") -and $mixedText.Contains("stderr-line")) "Mixed stdout/stderr output was not preserved."

$failureLog = Join-Path $testDir "failure.log"
$failed = $false
try { Invoke-AtlasNative -FilePath "cmd.exe" -ArgumentList @("/c", "echo failure-stderr 1>&2&exit /b 7") -LogPath $failureLog | Out-Null }
catch { $failed = $true }
Assert $failed "A nonzero native exit code must fail the invocation."
Assert ((Get-Content -Raw $failureLog).Contains("failure-stderr")) "Failure stderr was not preserved."

Remove-Item -LiteralPath $testDir -Recurse -Force
Write-Output "Native command regression tests passed."
