@echo off
setlocal

cd /d "%~dp0\.."
if not exist "logs" mkdir "logs"

echo [%date% %time%] start snapshot_fine_table >> "logs\snapshot_fine_table.log"
"D:\python\python.exe" -m scripts.snapshot_fine_table --previous-day >> "logs\snapshot_fine_table.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end snapshot_fine_table errorlevel=%EXIT_CODE% >> "logs\snapshot_fine_table.log"

exit /b %EXIT_CODE%
