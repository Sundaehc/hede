@echo off
setlocal

cd /d "%~dp0\.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "Hede Fine Table Export Daily" --log-file "logs\export_fine_table_daily.log" -- "%PYTHON%" -m scripts.export_fine_table_daily %*
exit /b %ERRORLEVEL%
