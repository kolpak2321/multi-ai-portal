$ErrorActionPreference='Stop'
$portalPidPath=Join-Path $PSScriptRoot '.sites-runtime\browser-bridge.pid'
if(Test-Path -LiteralPath $portalPidPath){
    $portalBridgePid=[int](Get-Content -LiteralPath $portalPidPath)
    $portalProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$portalBridgePid" -ErrorAction SilentlyContinue
    if($portalProcess -and $portalProcess.CommandLine -like '*browser-dispatcher.mjs*'){Stop-Process -Id $portalBridgePid;Write-Host 'Обработчик вкладок остановлен.'}
}
