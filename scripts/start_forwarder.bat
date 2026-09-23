@echo off
setlocal
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "VALIDATION_HOME=%ROOT%"
set "PYTHONPATH=%ROOT%;%PYTHONPATH%"
cd /d "%ROOT%"
py -3 -m forwarder.app.main --config forwarder/config/forwarder.yaml
