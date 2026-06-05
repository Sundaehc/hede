@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start import_suppliers_weekly >> "logs\import_suppliers_weekly.log"
"D:\python\python.exe" -m scripts.import_suppliers_from_units >> "logs\import_suppliers_weekly.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end import_suppliers_weekly errorlevel=%EXIT_CODE% >> "logs\import_suppliers_weekly.log"

endlocal & exit /b %EXIT_CODE%
