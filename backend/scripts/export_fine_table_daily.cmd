@echo off
setlocal

cd /d "%~dp0\.."
if not exist "logs" mkdir "logs"

echo [%date% %time%] start export_fine_table_daily >> "logs\export_fine_table_daily.log"
"D:\python\python.exe" -m scripts.export_fine_table_daily %* >> "logs\export_fine_table_daily.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end export_fine_table_daily errorlevel=%EXIT_CODE% >> "logs\export_fine_table_daily.log"

exit /b %EXIT_CODE%
