$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$portalEnvPath = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $portalEnvPath)) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '.env.example') -Destination $portalEnvPath
}
$portalConfig = [System.IO.File]::ReadAllText($portalEnvPath)
foreach ($portalSetting in @('APP_ACCESS_TOKEN', 'POSTGRES_PASSWORD', 'PORTAL_LOGIN_PASSWORD')) {
    if($portalConfig -notmatch "(?m)^$portalSetting="){$portalConfig += "`n$portalSetting=`n"}
    if ($portalConfig -match "(?m)^$portalSetting=\s*$") {
        $portalBytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($portalBytes)
        $portalValue = [Convert]::ToHexString($portalBytes).ToLowerInvariant()
        $portalConfig = [regex]::Replace($portalConfig, "(?m)^$portalSetting=\s*$", "$portalSetting=$portalValue")
    }
}
[System.IO.File]::WriteAllText($portalEnvPath, $portalConfig, (New-Object System.Text.UTF8Encoding($false)))
if($portalConfig -notmatch '(?m)^PORTAL_ALLOWED_ORIGINS='){$portalConfig += "`nPORTAL_ALLOWED_ORIGINS=https://kolpak2321.github.io`n";[System.IO.File]::WriteAllText($portalEnvPath,$portalConfig,(New-Object System.Text.UTF8Encoding($false)))}
& (Join-Path $PSScriptRoot 'stop-browser-bridge.ps1')
docker compose -f compose.yaml -f compose.browser.yaml up -d --build db api worker web
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed' }
& (Join-Path $PSScriptRoot 'start-bridge.ps1')
$portalPort = if ($portalConfig -match '(?m)^PORTAL_PORT=(\d+)') { $Matches[1] } else { '8086' }
Write-Host "Portal: http://localhost:$portalPort"
Write-Host 'Для веб-моделей: start-chrome.ps1, ручной вход, затем start-python-bridge.ps1.'
