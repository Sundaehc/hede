@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "hede_import_gj_merged_product_info_daily" --log-file "logs\import_gj_merged_product_info.log" -- "D:\python\python.exe" -m scripts.import_gj_merged_product_info_daily --lookback-days 7 --retry-until 16:00 --retry-interval-seconds 1800
exit /b %ERRORLEVEL%
