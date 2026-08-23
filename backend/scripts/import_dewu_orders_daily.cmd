@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportDewuOrders" --log-file "logs\import_dewu_orders_daily.log" -- "D:\python\python.exe" -m scripts.import_dewu_orders_daily
exit /b %ERRORLEVEL%
