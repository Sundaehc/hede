@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start import_daily_sales_reports >> "logs\import_daily_sales_reports.log"
"D:\python\python.exe" -m scripts.import_daily_sales_reports >> "logs\import_daily_sales_reports.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end import_daily_sales_reports errorlevel=%EXIT_CODE% >> "logs\import_daily_sales_reports.log"

endlocal & exit /b %EXIT_CODE%
