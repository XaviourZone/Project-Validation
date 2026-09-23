@echo off
setlocal
set ROOT=%~dp0
set PG=%ROOT%windows-x64
set DATA=%ROOT%data
if not exist "%DATA%\PG_VERSION" (
  if not exist "%PG%\bin\initdb.exe" (echo ERROR: PostgreSQL binaries missing&exit /b 1)
  "%PG%\bin\initdb.exe" -D "%DATA%" -U validation -A scram-sha-256 -E UTF8
  if errorlevel 1 exit /b 1
)
"%PG%\bin\pg_ctl.exe" -D "%DATA%" status >nul 2>&1
if not errorlevel 1 (echo PostgreSQL already running&exit /b 0)
"%PG%\bin\pg_ctl.exe" -D "%DATA%" -l "%ROOT%postgres.log" -o "-p 5432" start
endlocal
