@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportPriceDaily" --log-file "logs\import_price_daily.log" -- "D:\python\python.exe" -m scripts.import_price_daily --lookback-days 7 --retry-until 16:00 --retry-interval-seconds 1800
exit /b %ERRORLEVEL%
