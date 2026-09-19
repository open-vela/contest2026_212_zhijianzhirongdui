@echo off
setlocal
cd /d "%~dp0.."
if not exist ".env" copy /Y ".env.example" ".env" >nul
docker compose --env-file .env down --remove-orphans
exit /b %errorlevel%
