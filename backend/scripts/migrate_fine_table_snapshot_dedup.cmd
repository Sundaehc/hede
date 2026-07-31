@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start migrate_fine_table_snapshot_dedup >> "logs\migrate_fine_table_snapshot_dedup.log"
"D:\python\python.exe" -m scripts.migrate_fine_table_snapshot_dedup >> "logs\migrate_fine_table_snapshot_dedup.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end migrate_fine_table_snapshot_dedup errorlevel=%EXIT_CODE% >> "logs\migrate_fine_table_snapshot_dedup.log"

endlocal & exit /b %EXIT_CODE%
