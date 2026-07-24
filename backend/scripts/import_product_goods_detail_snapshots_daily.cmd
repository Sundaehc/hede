@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start snapshot_product_goods >> "logs\snapshot_product_goods.log"
"D:\python\python.exe" -m scripts.snapshot_product_goods --previous-day >> "logs\snapshot_product_goods.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end snapshot_product_goods errorlevel=%EXIT_CODE% >> "logs\snapshot_product_goods.log"

endlocal & exit /b %EXIT_CODE%
