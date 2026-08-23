@echo off
setlocal
cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeMasterDataSync" --log-file "logs\master_data_sync.log" -- "D:\python\python.exe" -m scripts.sync_master_data_daily %*
exit /b %ERRORLEVEL%
