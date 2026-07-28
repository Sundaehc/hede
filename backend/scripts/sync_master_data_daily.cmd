@echo off
setlocal
cd /d "%~dp0.."
if not exist "logs" mkdir "logs"

echo [%date% %time%] start master_data_sync >> "logs\master_data_sync.log"
"D:\python\python.exe" -m scripts.sync_master_data_daily %* >> "logs\master_data_sync.log" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] end master_data_sync errorlevel=%EXIT_CODE% >> "logs\master_data_sync.log"
exit /b %EXIT_CODE%
