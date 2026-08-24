@echo off
setlocal

cd /d "%~dp0.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "HedeBackfillProductGoodsDetailSnapshots" --log-file "logs\import_product_goods_detail_snapshots.log" -- "%PYTHON%" -m scripts.import_product_goods_detail_snapshots
exit /b %ERRORLEVEL%
