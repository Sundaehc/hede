@echo off
setlocal
cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeDatabaseMaintenance" --log-file "logs\database_maintenance.log" -- "D:\python\python.exe" -m scripts.maintain_database %*
exit /b %ERRORLEVEL%
