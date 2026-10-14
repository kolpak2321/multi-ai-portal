$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$portalPython='C:\Users\Sklad\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if(-not(Test-Path -LiteralPath $portalPython)){$portalPython=(Get-Command python -ErrorAction Stop).Source}
if(-not(Test-Path -LiteralPath '.sites-runtime\python-deps\playwright')){throw 'Установите зависимости: python -m pip install --target .sites-runtime/python-deps playwright==1.58.0 httpx==0.28.1'}
$null=Invoke-RestMethod 'http://127.0.0.1:19222/json/version' -TimeoutSec 3
$portalListener=Get-NetTCPConnection -LocalPort 19222 -State Listen | Select-Object -First 1
$portalOwner=Get-CimInstance Win32_Process -Filter "ProcessId=$($portalListener.OwningProcess)"
$portalProfile=Join-Path $PSScriptRoot '.sites-runtime\chrome-profile'
if($portalOwner.CommandLine -notlike "*$portalProfile*"){throw 'Порт принадлежит другому браузеру; подключение запрещено.'}
docker compose -f compose.yaml -f compose.browser.yaml stop deepseek zai
& (Join-Path $PSScriptRoot 'stop-browser-bridge.ps1')
foreach($portalProvider in @('deepseek','zai')){
    $portalPidFile=Join-Path $PSScriptRoot ('.sites-runtime\python-'+$portalProvider+'.pid')
    if(Test-Path -LiteralPath $portalPidFile){
        $portalOldPid=[int](Get-Content -LiteralPath $portalPidFile)
        $portalOldProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$portalOldPid" -ErrorAction SilentlyContinue
        if($portalOldProcess -and $portalOldProcess.CommandLine -like '*python-browser.py*' -and $portalOldProcess.CommandLine -like "*$portalProvider*"){continue}
    }
    $portalProcess=Start-Process -FilePath $portalPython -ArgumentList @('-u',('"'+(Join-Path $PSScriptRoot 'bridge\python-browser.py')+'"'),$portalProvider) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot ('.sites-runtime\python-'+$portalProvider+'.log')) -RedirectStandardError (Join-Path $PSScriptRoot ('.sites-runtime\python-'+$portalProvider+'-error.log'))
    Set-Content -LiteralPath $portalPidFile -Value $portalProcess.Id
}
Write-Host 'Два независимых Python-обработчика подключены к Chrome.'
