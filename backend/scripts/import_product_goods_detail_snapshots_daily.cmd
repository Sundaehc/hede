@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start import_product_goods_detail_snapshots_daily >> "logs\import_product_goods_detail_snapshots_daily.log"
"D:\python\python.exe" -m scripts.import_product_goods_detail_snapshots --max-workbooks 1 --force >> "logs\import_product_goods_detail_snapshots_daily.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end import_product_goods_detail_snapshots_daily errorlevel=%EXIT_CODE% >> "logs\import_product_goods_detail_snapshots_daily.log"

endlocal & exit /b %EXIT_CODE%
