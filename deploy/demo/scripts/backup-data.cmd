@echo off
setlocal
cd /d "%~dp0.."
if not exist ".env" copy /Y ".env.example" ".env" >nul

echo [INFO] Stopping app and MQTT briefly for a consistent backup...
docker compose --env-file .env stop app mqtt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup-data.ps1"
set "BACKUP_RESULT=%errorlevel%"
docker compose --env-file .env start mqtt app
exit /b %BACKUP_RESULT%
