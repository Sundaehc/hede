@echo off
setlocal
cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "smiley-daily-import" --log-file "logs\smiley_daily_import.log" --working-directory "E:\smiley" -- "D:\python\python.exe" "E:\smiley\main.py"
exit /b %ERRORLEVEL%
