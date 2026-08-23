@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportDailySalesReports" --log-file "logs\import_daily_sales_reports.log" -- "D:\python\python.exe" -m scripts.import_daily_sales_reports
exit /b %ERRORLEVEL%
