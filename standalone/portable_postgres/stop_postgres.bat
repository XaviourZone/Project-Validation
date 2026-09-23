@echo off
setlocal
set ROOT=%~dp0
"%ROOT%windows-x64\bin\pg_ctl.exe" -D "%ROOT%data" stop -m fast
endlocal
