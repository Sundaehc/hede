@echo off
setlocal

cd /d "%~dp0.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "HedeImportVipDailySalesReport" --log-file "logs\import_vip_daily_sales_report.log" -- "%PYTHON%" -m scripts.import_daily_sales_reports --source vip
exit /b %ERRORLEVEL%
