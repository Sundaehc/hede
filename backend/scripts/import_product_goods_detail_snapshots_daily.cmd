@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportProductGoodsDetailSnapshotsDaily" --log-file "logs\snapshot_product_goods.log" -- "D:\python\python.exe" -m scripts.snapshot_product_goods --previous-day
exit /b %ERRORLEVEL%
