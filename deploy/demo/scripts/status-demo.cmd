@echo off
setlocal
cd /d "%~dp0.."
if not exist ".env" copy /Y ".env.example" ".env" >nul
docker compose --env-file .env ps
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0smoke-test.ps1"
exit /b %errorlevel%
