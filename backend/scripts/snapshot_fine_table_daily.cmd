@echo off
setlocal

cd /d "%~dp0\.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "Hede Fine Table Snapshot Daily" --log-file "logs\snapshot_fine_table.log" -- "%PYTHON%" -m scripts.snapshot_fine_table --previous-day
exit /b %ERRORLEVEL%
