@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "VALIDATION_HOME=%ROOT%"
if defined PYTHONPATH (set "PYTHONPATH=%ROOT%;%PYTHONPATH%") else (set "PYTHONPATH=%ROOT%")
cd /d "%ROOT%"

echo ================================================
echo          VALIDATION SYSTEM STARTUP
echo ================================================
echo.
echo [1/2] Preparing local Python environment...
py -3 "%ROOT%\scripts\setup_dependencies.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency bootstrap failed.
    exit /b 1
)

set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] Validation Python environment not found: %PY%
    exit /b 1
)

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
if not exist "%ROOT%\run" mkdir "%ROOT%\run"
if not exist "%ROOT%\DATA_INFLOW\SAIS_IOR" mkdir "%ROOT%\DATA_INFLOW\SAIS_IOR"
if not exist "%ROOT%\DATA_INFLOW\SAIS_GLOBAL" mkdir "%ROOT%\DATA_INFLOW\SAIS_GLOBAL"
if not exist "%ROOT%\DATA_INFLOW\MSIS" mkdir "%ROOT%\DATA_INFLOW\MSIS"
if not exist "%ROOT%\DATA_INFLOW\LRIT" mkdir "%ROOT%\DATA_INFLOW\LRIT"
if not exist "%ROOT%\forwarder\spool\pending" mkdir "%ROOT%\forwarder\spool\pending"
if not exist "%ROOT%\forwarder\spool\delivered" mkdir "%ROOT%\forwarder\spool\delivered"
if not exist "%ROOT%\forwarder\spool\failed" mkdir "%ROOT%\forwarder\spool\failed"
if not exist "%ROOT%\router\state" mkdir "%ROOT%\router\state"
if not exist "%ROOT%\parser\state" mkdir "%ROOT%\parser\state"
if not exist "%ROOT%\parser\reference" mkdir "%ROOT%\parser\reference"
if not exist "%ROOT%\forwarder\state" mkdir "%ROOT%\forwarder\state"

echo.
echo [2/2] Starting independent services in background...
echo.

start "" /b "%PY%" "%ROOT%\scripts\launch_service.py" router router.app.main --config router/config/sources.yaml
start "" /b "%PY%" "%ROOT%\scripts\launch_service.py" parser parser.app.main --config parser/config/parser.yaml
start "" /b "%PY%" "%ROOT%\scripts\launch_service.py" forwarder forwarder.app.main --config forwarder/config/forwarder.yaml
start "" /b "%PY%" "%ROOT%\scripts\launch_service.py" console console.app.main

echo.
echo ================================================
echo          VALIDATION SYSTEM STARTED
echo ================================================
echo.
echo Operator Console:
echo   http://127.0.0.1:8080
echo.
echo Router, Parser and Forwarder run independently
echo in the background. This is the only launcher
echo terminal; service output is stored in logs\.
echo.
echo Logs:
echo   logs\router.log
echo   logs\parser.log
echo   logs\forwarder.log
echo   logs\console.log
echo ================================================
echo.
endlocal
