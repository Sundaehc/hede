@echo off
setlocal

cd /d "%~dp0.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "HedeImportDailySalesReports" --log-file "logs\import_daily_sales_reports.log" -- "%PYTHON%" -m scripts.import_daily_sales_reports --source jst --require-previous-day --retry-until 16:00 --retry-interval-seconds 1800 --skip-product-goods-refresh
exit /b %ERRORLEVEL%
