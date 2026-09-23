@echo off
set ROOT=%~dp0..
python "%ROOT%\db\start_postgres.py"
if errorlevel 1 exit /b 1
python "%ROOT%\db\db_manager.py"
