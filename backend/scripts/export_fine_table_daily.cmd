@echo off
setlocal

cd /d "%~dp0\.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "Hede Fine Table Export Daily" --log-file "logs\export_fine_table_daily.log" -- "D:\python\python.exe" -m scripts.export_fine_table_daily %*
exit /b %ERRORLEVEL%
