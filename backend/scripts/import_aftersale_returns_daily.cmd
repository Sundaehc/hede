@echo off
setlocal

cd /d "%~dp0\.."
if not exist "logs" mkdir "logs"

echo [%date% %time%] start import_aftersale_returns_daily >> "logs\import_aftersale_returns_daily.log"
"D:\python\python.exe" -m scripts.import_aftersale_returns_daily %* >> "logs\import_aftersale_returns_daily.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end import_aftersale_returns_daily errorlevel=%EXIT_CODE% >> "logs\import_aftersale_returns_daily.log"

endlocal & exit /b %EXIT_CODE%
