@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start import_jst_daily >> "logs\import_jst_daily.log"
"D:\python\python.exe" -m scripts.import_jst_daily >> "logs\import_jst_daily.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end import_jst_daily errorlevel=%EXIT_CODE% >> "logs\import_jst_daily.log"

endlocal & exit /b %EXIT_CODE%
