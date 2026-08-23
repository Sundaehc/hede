@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportProductsDaily" --log-file "logs\import_products.log" -- "D:\python\python.exe" -m cli sync
exit /b %ERRORLEVEL%
