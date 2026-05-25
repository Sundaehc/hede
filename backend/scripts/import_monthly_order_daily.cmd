@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start import_monthly_order >> "logs\import_monthly_order.log"
"D:\python\python.exe" -m scripts.import_monthly_order >> "logs\import_monthly_order.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end import_monthly_order errorlevel=%EXIT_CODE% >> "logs\import_monthly_order.log"

endlocal & exit /b %EXIT_CODE%
