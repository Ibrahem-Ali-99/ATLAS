function Invoke-AtlasNative {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter()][string[]]$ArgumentList = @(),
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter()][switch]$AllowFailure
  )

  $oldErrorAction = $ErrorActionPreference
  $hasNativePreference = $null -ne (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)
  $oldNativePreference = $null
  if ($hasNativePreference) { $oldNativePreference = $PSNativeCommandUseErrorActionPreference }
  try {
    # Windows PowerShell promotes native stderr to ErrorRecord objects. Keep the
    # stream visible and logged, but let the process exit code decide success.
    $ErrorActionPreference = "Continue"
    if ($hasNativePreference) { $PSNativeCommandUseErrorActionPreference = $false }
    & $FilePath @ArgumentList 2>&1 | Tee-Object -FilePath $LogPath | Out-Host
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $oldErrorAction
    if ($hasNativePreference) { $PSNativeCommandUseErrorActionPreference = $oldNativePreference }
  }
  if ($exitCode -ne 0 -and -not $AllowFailure) {
    throw "Native command failed with exit code ${exitCode}: $FilePath $($ArgumentList -join ' ')"
  }
  return $exitCode
}
