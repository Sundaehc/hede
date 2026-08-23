@echo off
setlocal

cd /d "%~dp0\.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportAftersaleReturnsDaily" --log-file "logs\import_aftersale_returns_daily.log" -- "D:\python\python.exe" -m scripts.import_aftersale_returns_daily %*
exit /b %ERRORLEVEL%
