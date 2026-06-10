@echo off
:: Start V1 and V2 paper bot instances on Windows
:: Usage: scripts\start_all.bat
::        scripts\start_all.bat stop

setlocal
set PROJECT_ROOT=%~dp0..
set LOGS_DIR=%PROJECT_ROOT%\logs

if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"

if /i "%1"=="stop" goto :stop

echo Starting instances...

:: V1 — paper, port 8000
start "polymarket-v1" /B cmd /c "set ENV_FILE=%PROJECT_ROOT%\.env && python -m uvicorn backend.main:app --port 8000 --loop asyncio >> %LOGS_DIR%\backend_v1.log 2>&1"
echo   Started V1 (port 8000) ^> logs\backend_v1.log

:: V2 — paper + calibration, port 8011
start "polymarket-v2" /B cmd /c "set ENV_FILE=%PROJECT_ROOT%\.env.v2 && python -m uvicorn backend.main:app --port 8011 --loop asyncio >> %LOGS_DIR%\backend_v2.log 2>&1"
echo   Started V2 (port 8011) ^> logs\backend_v2.log

echo.
echo To tail logs:
echo   powershell Get-Content logs\backend_v1.log -Wait
echo   powershell Get-Content logs\backend_v2.log -Wait
echo.
echo To stop: scripts\start_all.bat stop
goto :eof

:stop
echo Stopping instances...
taskkill /FI "WINDOWTITLE eq polymarket-v1" /F >nul 2>&1 && echo   Stopped V1 || echo   V1 was not running
taskkill /FI "WINDOWTITLE eq polymarket-v2" /F >nul 2>&1 && echo   Stopped V2 || echo   V2 was not running
echo Done.
