@echo off
setlocal
cd /d "%~dp0.."
if not exist "images\dominiscius-demo-images.tar" (
  echo [ERROR] images\dominiscius-demo-images.tar not found.
  exit /b 2
)
docker load -i "images\dominiscius-demo-images.tar"
exit /b %errorlevel%
