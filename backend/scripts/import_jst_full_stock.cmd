@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportJstFullStock" --log-file "logs\import_jst_full_stock.log" -- "D:\python\python.exe" -m scripts.import_jst_full_stock
exit /b %ERRORLEVEL%
