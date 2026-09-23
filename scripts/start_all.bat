@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "VALIDATION_HOME=%ROOT%"
if defined PYTHONPATH (set "PYTHONPATH=%ROOT%;%PYTHONPATH%") else (set "PYTHONPATH=%ROOT%")
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
cd /d "%ROOT%"
start "VALIDATION ROUTER" cmd /k "cd /d ""%ROOT%"" && set ""VALIDATION_HOME=%ROOT%"" && set ""PYTHONPATH=%PYTHONPATH%"" && py -3 -m router.app.main --config router/config/sources.yaml"
start "VALIDATION PARSER" cmd /k "cd /d ""%ROOT%"" && set ""VALIDATION_HOME=%ROOT%"" && set ""PYTHONPATH=%PYTHONPATH%"" && py -3 -m parser.app.main --config parser/config/parser.yaml"
start "VALIDATION FORWARDER" cmd /k "cd /d ""%ROOT%"" && set ""VALIDATION_HOME=%ROOT%"" && set ""PYTHONPATH=%PYTHONPATH%"" && py -3 -m forwarder.app.main --config forwarder/config/forwarder.yaml"
start "VALIDATION CONSOLE" cmd /k "cd /d ""%ROOT%"" && set ""VALIDATION_HOME=%ROOT%"" && set ""PYTHONPATH=%PYTHONPATH%"" && py -3 -m console.app.main"
echo.
echo VALIDATION started: Router, Parser, Forwarder and Console are separate processes.
echo Console: http://127.0.0.1:8080
echo Router: http://127.0.0.1:18080
echo Parser: http://127.0.0.1:18081
echo Forwarder: http://127.0.0.1:18082
endlocal
