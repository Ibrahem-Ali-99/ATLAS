param([switch]$WithN8n)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot "native-command.ps1")
Push-Location $repo
try {
  $services = @("postgres", "mailpit")
  if ($WithN8n) { $services += "n8n" }
  Invoke-AtlasNative -FilePath "docker" -ArgumentList (@("compose", "stop") + $services) -LogPath (Join-Path $repo "var\dev\compose-stop.log") | Out-Null
  Write-Output "Stopped ATLAS infrastructure services. Volumes and databases were preserved."
  Write-Output "Host API/web PowerShell windows are left untouched; close only the ATLAS windows started by start-dev.ps1."
} finally { Pop-Location }
