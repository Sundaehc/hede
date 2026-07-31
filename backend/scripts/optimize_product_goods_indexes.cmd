@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start optimize_product_goods_indexes >> "logs\optimize_product_goods_indexes.log"
"D:\python\python.exe" -m scripts.optimize_product_goods_indexes >> "logs\optimize_product_goods_indexes.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end optimize_product_goods_indexes errorlevel=%EXIT_CODE% >> "logs\optimize_product_goods_indexes.log"

endlocal & exit /b %EXIT_CODE%
