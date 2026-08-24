@echo off
setlocal

cd /d "%~dp0.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "HedeImportProductsDaily" --log-file "logs\import_products.log" -- "%PYTHON%" -m scripts.sync_products_daily
exit /b %ERRORLEVEL%
