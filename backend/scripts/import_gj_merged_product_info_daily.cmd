@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start import_gj_merged_product_info_daily >> "logs\import_gj_merged_product_info.log"
"D:\python\python.exe" -m scripts.import_gj_merged_product_info_daily --lookback-days 7 --retry-until 16:00 --retry-interval-seconds 1800 >> "logs\import_gj_merged_product_info.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end import_gj_merged_product_info_daily errorlevel=%EXIT_CODE% >> "logs\import_gj_merged_product_info.log"

endlocal & exit /b %EXIT_CODE%
