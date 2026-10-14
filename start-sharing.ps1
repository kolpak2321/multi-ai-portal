$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
docker compose -f compose.yaml -f compose.browser.yaml --profile share up -d tunnel
if($LASTEXITCODE -ne 0){throw 'Не удалось запустить HTTPS-туннель'}
Write-Host 'HTTPS-адрес серверной части (может измениться после перезапуска):'
docker compose -f compose.yaml -f compose.browser.yaml logs --tail=50 tunnel
