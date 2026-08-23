@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportVipDaily" --log-file "logs\import_vip_daily.log" -- "D:\python\python.exe" -m scripts.import_vip_daily
exit /b %ERRORLEVEL%
