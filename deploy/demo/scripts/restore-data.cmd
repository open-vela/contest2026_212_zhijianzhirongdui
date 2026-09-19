@echo off
setlocal
if "%~1"=="" (
  echo Usage: restore-data.cmd ^<backups\dominiscius-data-YYYYMMDD-HHMMSS.zip^>
  exit /b 2
)
cd /d "%~dp0.."
if not exist ".env" copy /Y ".env.example" ".env" >nul
if not exist "%~1" (
  echo [ERROR] Backup archive not found: %~1
  exit /b 2
)
docker compose --env-file .env stop app mqtt
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%~f1' -DestinationPath '%CD%' -Force"
set "RESTORE_RESULT=%errorlevel%"
docker compose --env-file .env start mqtt app
exit /b %RESTORE_RESULT%
