@echo off
setlocal
cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeOrderHistoryTiering" --log-file "logs\order_history_tiering.log" -- "D:\python\python.exe" -m scripts.manage_order_history_tiers --apply %*
exit /b %ERRORLEVEL%
