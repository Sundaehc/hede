@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start sync_jst_stock >> "logs\sync_jst_stock.log"
"D:\python\python.exe" -m scripts.sync_jst_stock >> "logs\sync_jst_stock.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end sync_jst_stock errorlevel=%EXIT_CODE% >> "logs\sync_jst_stock.log"

endlocal & exit /b %EXIT_CODE%
