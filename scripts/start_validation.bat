@echo off
setlocal EnableExtensions

REM Validation Windows startup
REM Starts Forwarder, Parser and Router as separate processes.

set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

set "VALIDATION_HOME=%ROOT%"
if defined PYTHONPATH (
    set "PYTHONPATH=%ROOT%;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%ROOT%"
)

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
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

cd /d "%ROOT%"

echo [VALIDATION] Starting Forwarder...
start "Validation Forwarder" cmd /k "cd /d ""%ROOT%"" && set ""VALIDATION_HOME=%ROOT%"" && set ""PYTHONPATH=%PYTHONPATH%"" && py -3 -m forwarder.app.main --config ""%ROOT%\forwarder\config\forwarder.yaml"" > ""%ROOT%\logs\forwarder.log"" 2>&1"

timeout /t 1 /nobreak >nul

echo [VALIDATION] Starting Parser...
start "Validation Parser" cmd /k "cd /d ""%ROOT%"" && set ""VALIDATION_HOME=%ROOT%"" && set ""PYTHONPATH=%PYTHONPATH%"" && py -3 -m parser.app.main --config ""%ROOT%\parser\config\parser.yaml"" > ""%ROOT%\logs\parser.log"" 2>&1"

timeout /t 2 /nobreak >nul

echo [VALIDATION] Starting Router...
start "Validation Router" cmd /k "cd /d ""%ROOT%"" && set ""VALIDATION_HOME=%ROOT%"" && set ""PYTHONPATH=%PYTHONPATH%"" && py -3 -m router.app.main --config ""%ROOT%\router\config\sources.yaml"" > ""%ROOT%\logs\router.log"" 2>&1"

echo.
echo [VALIDATION] Forwarder, Parser and Router startup commands issued.
echo [VALIDATION] Root: %ROOT%
echo [VALIDATION] APIs: Router 8080, Parser 8081, Forwarder 8082
echo.
echo Close each service window with Ctrl+C to stop that service.
echo.
pause
