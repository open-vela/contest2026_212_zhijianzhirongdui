@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0smoke-test.ps1"
exit /b %errorlevel%
