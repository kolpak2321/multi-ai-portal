$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$portalChrome='C:\Program Files\Google\Chrome\Application\chrome.exe'
if(-not(Test-Path -LiteralPath $portalChrome)){$portalChrome='C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'}
if(-not(Test-Path -LiteralPath $portalChrome)){throw 'Google Chrome не найден'}
$portalProfile=Join-Path $PSScriptRoot '.sites-runtime\chrome-profile'
# Use a dedicated profile. No automation-masking flags or personal Chrome data.
try{
    $portalExisting=Invoke-RestMethod 'http://127.0.0.1:19222/json/version' -TimeoutSec 2
    if($portalExisting.Browser){
        $portalListener=Get-NetTCPConnection -LocalPort 19222 -State Listen | Select-Object -First 1
        $portalOwner=Get-CimInstance Win32_Process -Filter "ProcessId=$($portalListener.OwningProcess)"
        if($portalOwner.CommandLine -notlike "*$portalProfile*"){throw 'Порт 19222 занят другим браузером. Подключение запрещено.'}
        Write-Host 'Chrome портала уже открыт.';exit 0
    }
}catch{if($_.Exception.Message -like '*занят другим браузером*'){throw}}
Start-Process -FilePath $portalChrome -ArgumentList @('--remote-debugging-address=127.0.0.1','--remote-debugging-port=19222',('--user-data-dir="'+$portalProfile+'"'),'--no-first-run','--no-default-browser-check','https://chat.deepseek.com/','https://chat.z.ai/') -WindowStyle Normal
Write-Host 'Открыл обычный Chrome с отдельным профилем портала. Сначала войдите в сервисы вручную, затем запустите start-python-bridge.ps1.'
