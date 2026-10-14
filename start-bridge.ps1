$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$portalNode=(Get-Command node -ErrorAction Stop).Source
$portalCodex=(Get-Command codex -ErrorAction Stop).Source
$env:PORTAL_CODEX_EXE=$portalCodex
$portalRuntime=Join-Path $PSScriptRoot '.sites-runtime'
New-Item -ItemType Directory -Path $portalRuntime -Force | Out-Null
$portalPidPath=Join-Path $portalRuntime 'codex-bridge.pid'
if(Test-Path -LiteralPath $portalPidPath) {
    $portalPreviousPid=[int](Get-Content -LiteralPath $portalPidPath)
    $portalPrevious=Get-CimInstance Win32_Process -Filter "ProcessId=$portalPreviousPid" -ErrorAction SilentlyContinue
    if($portalPrevious -and $portalPrevious.CommandLine -like '*codex-runner.mjs*') {
        Write-Host 'Обработчик уже работает.'
        exit 0
    }
    Remove-Item -LiteralPath $portalPidPath
}
$portalScript=Join-Path $PSScriptRoot 'bridge\codex-runner.mjs'
Start-Process -FilePath $portalNode -ArgumentList @('"'+$portalScript+'"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $portalRuntime 'bridge.log') -RedirectStandardError (Join-Path $portalRuntime 'bridge-error.log')
Write-Host 'Обработчик ChatGPT/Codex запущен в фоне.'
