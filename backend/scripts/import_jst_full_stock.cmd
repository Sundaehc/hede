@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start import_jst_full_stock >> "logs\import_jst_full_stock.log"
"D:\python\python.exe" -m scripts.import_jst_full_stock >> "logs\import_jst_full_stock.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end import_jst_full_stock errorlevel=%EXIT_CODE% >> "logs\import_jst_full_stock.log"

endlocal & exit /b %EXIT_CODE%
