@echo off
setlocal
cd /d "%~dp0.."
if not exist "logs" mkdir "logs"

echo [%date% %time%] start database_maintenance >> "logs\database_maintenance.log"
"D:\python\python.exe" -m scripts.maintain_database %* >> "logs\database_maintenance.log" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] end database_maintenance errorlevel=%EXIT_CODE% >> "logs\database_maintenance.log"
exit /b %EXIT_CODE%
