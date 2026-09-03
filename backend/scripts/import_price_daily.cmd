@echo off
setlocal

cd /d "%~dp0.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "HedeImportPriceDaily" --log-file "logs\import_price_daily.log" --skip-if-business-success "import_price_daily" -- "%PYTHON%" -m scripts.import_price_daily --lookback-days 7 --allow-missing-current
exit /b %ERRORLEVEL%
