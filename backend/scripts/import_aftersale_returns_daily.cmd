@echo off
setlocal

cd /d "%~dp0\.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportAftersaleReturnsDaily" --log-file "logs\import_aftersale_returns_daily.log" --skip-if-business-success "import_aftersale_returns_daily" -- "D:\python\python.exe" -m scripts.import_aftersale_returns_daily --retry-until 16:00 --retry-interval-seconds 1800 %*
exit /b %ERRORLEVEL%
