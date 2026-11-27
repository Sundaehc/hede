@echo off
setlocal

cd /d "%~dp0.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "HedeCheckStockQualityReportsDaily" --log-file "logs\check_stock_quality_reports.log" -- "%PYTHON%" -m scripts.check_stock_quality_reports_daily %*
exit /b %ERRORLEVEL%
