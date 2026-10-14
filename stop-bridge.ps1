$ErrorActionPreference='Stop'
$portalPidPath=Join-Path $PSScriptRoot '.sites-runtime\codex-bridge.pid'
if(Test-Path -LiteralPath $portalPidPath) {
    $portalBridgePid=[int](Get-Content -LiteralPath $portalPidPath)
    $portalProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$portalBridgePid" -ErrorAction SilentlyContinue
    if($portalProcess -and $portalProcess.CommandLine -like '*codex-runner.mjs*') {
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$portalBridgePid" | Where-Object {$_.Name -eq 'codex.exe'} | ForEach-Object {Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue}
        Stop-Process -Id $portalBridgePid -ErrorAction SilentlyContinue
        Write-Host 'Локальный обработчик остановлен.'
    }
}
