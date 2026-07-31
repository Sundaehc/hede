@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start ensure_fine_table_snapshot_content_indexes >> "logs\ensure_fine_table_snapshot_content_indexes.log"
"D:\python\python.exe" -m scripts.ensure_fine_table_snapshot_content_indexes >> "logs\ensure_fine_table_snapshot_content_indexes.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end ensure_fine_table_snapshot_content_indexes errorlevel=%EXIT_CODE% >> "logs\ensure_fine_table_snapshot_content_indexes.log"

endlocal & exit /b %EXIT_CODE%
