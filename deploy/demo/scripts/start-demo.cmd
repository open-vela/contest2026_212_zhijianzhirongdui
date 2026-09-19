@echo off
setlocal
cd /d "%~dp0.."

if not exist ".env" copy /Y ".env.example" ".env" >nul
for %%D in ("data\app" "data\mqtt" "logs\app" "logs\mqtt" "backups" "images") do if not exist "%%~D" mkdir "%%~D"

docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Desktop is not running.
  exit /b 1
)

set "DOMINISCIUS_IMAGE=dominiscius-demo:0.2.0"
for /f "usebackq tokens=1,* delims==" %%A in (".env") do if /I "%%A"=="DOMINISCIUS_IMAGE" set "DOMINISCIUS_IMAGE=%%B"
set "NEED_IMAGE_IMPORT=0"
docker image inspect "%DOMINISCIUS_IMAGE%" >nul 2>&1
if errorlevel 1 set "NEED_IMAGE_IMPORT=1"
docker image inspect "eclipse-mosquitto:2.0.20" >nul 2>&1
if errorlevel 1 set "NEED_IMAGE_IMPORT=1"

if "%NEED_IMAGE_IMPORT%"=="1" (
  if exist "images\dominiscius-demo-images.tar" (
    echo [INFO] Importing offline images...
    docker load -i "images\dominiscius-demo-images.tar"
    if errorlevel 1 exit /b 1
  ) else (
    echo [ERROR] App image is missing and images\dominiscius-demo-images.tar was not found.
    exit /b 1
  )
)

docker image inspect "%DOMINISCIUS_IMAGE%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] App image is still missing after offline import.
  exit /b 1
)
docker image inspect "eclipse-mosquitto:2.0.20" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Mosquitto image is still missing after offline import.
  exit /b 1
)

docker compose --env-file .env up -d --no-build
if errorlevel 1 exit /b 1

call "%~dp0smoke-test.cmd"
exit /b %errorlevel%
