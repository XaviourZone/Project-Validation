@echo off
setlocal
set ROOT=%~dp0..
for %%I in ("%ROOT%") do set ROOT=%%~fI
if "%PYTHON%"=="" (set PYTHON=py -3)
%PYTHON% "%ROOT%\standalone\db\start_postgres.py"
if errorlevel 1 exit /b 1
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
if not exist "%ROOT%\run" mkdir "%ROOT%\run"
start "" /b %PYTHON% "%ROOT%\standalone\db\db_manager.py"
for %%F in (SAIS_IOR SAIS_GLOBAL MSIS LRIT VATMS_EAST VATMS_WEST NAIS) do start "" /b %PYTHON% "%ROOT%\standalone\feeds\%%F.py"
echo VALIDATION standalone runtime started
echo DB console: http://127.0.0.1:5055
endlocal
