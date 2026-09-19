$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackupDir = Join-Path $Root "backups"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Archive = Join-Path $BackupDir "dominiscius-data-$Stamp.zip"
$Paths = @((Join-Path $Root "data"), (Join-Path $Root "logs")) | Where-Object { Test-Path $_ }
if ($Paths.Count -eq 0) { throw "No data or log directory exists." }
Compress-Archive -Path $Paths -DestinationPath $Archive -CompressionLevel Optimal
Write-Host "[OK] Backup created: $Archive"
