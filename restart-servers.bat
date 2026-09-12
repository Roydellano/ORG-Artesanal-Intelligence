@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\restart-servers.ps1"
set "result=%errorlevel%"
echo.
pause
exit /b %result%
