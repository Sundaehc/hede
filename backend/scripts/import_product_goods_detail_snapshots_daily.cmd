@echo off
setlocal

cd /d "%~dp0.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "HedeImportProductGoodsDetailSnapshotsDaily" --log-file "logs\snapshot_product_goods.log" -- "%PYTHON%" -m scripts.snapshot_product_goods --previous-day
exit /b %ERRORLEVEL%
