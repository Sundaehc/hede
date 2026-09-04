@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportJstDaily" --log-file "logs\import_jst_daily.log" --skip-if-business-success "import_jst_daily" -- "D:\python\python.exe" -m scripts.import_jst_daily
exit /b %ERRORLEVEL%
