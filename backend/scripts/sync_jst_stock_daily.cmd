@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "Hede_JST_Stock_Sync" --log-file "logs\sync_jst_stock.log" --skip-if-business-success "sync_jst_stock_daily" -- "D:\python\python.exe" -m scripts.sync_jst_stock
exit /b %ERRORLEVEL%
