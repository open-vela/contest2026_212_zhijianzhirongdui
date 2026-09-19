$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvFile = Join-Path $Root ".env"
$Port = 8000
if (Test-Path $EnvFile) {
    $PortLine = Get-Content $EnvFile | Where-Object { $_ -match '^APP_PORT=' } | Select-Object -Last 1
    if ($PortLine) { $Port = [int](($PortLine -split '=', 2)[1]) }
}
$Base = "http://127.0.0.1:$Port"

$LastError = $null
for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
    try {
        $Health = Invoke-RestMethod -Uri "$Base/health" -TimeoutSec 2
        if ($Health.status -eq "ok") { break }
    } catch { $LastError = $_ }
    Start-Sleep -Seconds 1
}
if (-not $Health -or $Health.status -ne "ok") { throw "Health check failed: $LastError" }

$Page = Invoke-WebRequest -UseBasicParsing -Uri "$Base/admin/demo" -TimeoutSec 5
if ($Page.StatusCode -ne 200 -or $Page.Headers['Content-Type'] -notmatch 'text/html') {
    throw "SPA route did not return HTML"
}
$Match = [regex]::Match($Page.Content, 'src="(/assets/[^"]+\.js)"')
if (-not $Match.Success) { throw "Vue JavaScript asset was not found in index.html" }
$Asset = Invoke-WebRequest -UseBasicParsing -Uri ($Base + $Match.Groups[1].Value) -TimeoutSec 5
if ($Asset.StatusCode -ne 200 -or $Asset.Headers['Content-Type'] -notmatch 'javascript') {
    throw "Vue JavaScript asset failed its status or Content-Type check"
}
$Favicon = Invoke-WebRequest -UseBasicParsing -Uri "$Base/favicon.svg" -TimeoutSec 5
if ($Favicon.StatusCode -ne 200 -or $Favicon.Headers['Content-Type'] -notmatch 'svg') {
    throw "favicon.svg failed its status or Content-Type check"
}
Write-Host "[OK] $Base/admin/demo, API health, Vue asset and favicon passed."
