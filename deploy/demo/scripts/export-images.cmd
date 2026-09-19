@echo off
setlocal
cd /d "%~dp0.."
if not exist ".env" copy /Y ".env.example" ".env" >nul
if not exist "images" mkdir "images"

set "DOMINISCIUS_IMAGE=dominiscius-demo:0.2.0"
for /f "usebackq tokens=1,* delims==" %%A in (".env") do if /I "%%A"=="DOMINISCIUS_IMAGE" set "DOMINISCIUS_IMAGE=%%B"

docker compose --env-file .env build app
if errorlevel 1 exit /b 1
docker pull eclipse-mosquitto:2.0.20
if errorlevel 1 exit /b 1
docker save -o "images\dominiscius-demo-images.tar" "%DOMINISCIUS_IMAGE%" eclipse-mosquitto:2.0.20
if errorlevel 1 exit /b 1
echo [OK] Offline images exported to images\dominiscius-demo-images.tar
