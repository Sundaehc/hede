@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeBackfillProductGoodsDetailSnapshots" --log-file "logs\import_product_goods_detail_snapshots.log" -- "D:\python\python.exe" -m scripts.import_product_goods_detail_snapshots
exit /b %ERRORLEVEL%
