@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportMonthlyOrder" --log-file "logs\import_monthly_order.log" -- "D:\python\python.exe" -m scripts.import_monthly_order
exit /b %ERRORLEVEL%
