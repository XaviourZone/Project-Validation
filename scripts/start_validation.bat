@echo off
setlocal EnableExtensions

REM Single-port Validation Console startup.
REM The Console starts and controls Router, Parser and Forwarder.

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

echo [VALIDATION] Starting single-port operator console on http://127.0.0.1:8080
if exist "%ROOT%\logs\console.log" del /q "%ROOT%\logs\console.log"

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    start "Validation Console" cmd /k "cd /d ""%ROOT%"" && set ""VALIDATION_HOME=%ROOT%"" && set ""PYTHONPATH=%PYTHONPATH%"" && py -3 -m console.app.main > ""%ROOT%\logs\console.log"" 2>&1"
) else (
    start "Validation Console" cmd /k "cd /d ""%ROOT%"" && set ""VALIDATION_HOME=%ROOT%"" && set ""PYTHONPATH=%PYTHONPATH%"" && python -m console.app.main > ""%ROOT%\logs\console.log"" 2>&1"
)

echo.
echo [VALIDATION] Console started.
echo [VALIDATION] Open: http://127.0.0.1:8080
echo [VALIDATION] Router / Parser / Forwarder are controlled from the console.
echo.
pause
