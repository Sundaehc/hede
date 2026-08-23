@echo off
setlocal

cd /d "%~dp0\.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "Hede Fine Table Snapshot Daily" --log-file "logs\snapshot_fine_table.log" -- "D:\python\python.exe" -m scripts.snapshot_fine_table --previous-day
exit /b %ERRORLEVEL%
