@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start import_products >> "logs\import_products.log"
"D:\python\python.exe" -m cli sync >> "logs\import_products.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end import_products errorlevel=%EXIT_CODE% >> "logs\import_products.log"

endlocal & exit /b %EXIT_CODE%
