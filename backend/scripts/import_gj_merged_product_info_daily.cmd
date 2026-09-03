@echo off
setlocal

cd /d "%~dp0.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "hede_import_gj_merged_product_info_daily" --log-file "logs\import_gj_merged_product_info.log" --skip-if-business-success "import_gj_merged_product_info_daily" -- "%PYTHON%" -m scripts.import_gj_merged_product_info_daily --lookback-days 7 --allow-missing-current
exit /b %ERRORLEVEL%
