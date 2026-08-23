@echo off
setlocal

cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportProductGoodsOrdersDaily" --log-file "logs\import_product_goods_historical_orders_daily.log" -- "D:\python\python.exe" -m scripts.import_product_goods_historical_orders_daily
exit /b %ERRORLEVEL%
