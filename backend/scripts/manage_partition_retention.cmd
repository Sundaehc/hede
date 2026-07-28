@echo off
setlocal
cd /d "%~dp0.."
if not exist "logs" mkdir "logs"

"D:\python\python.exe" -m scripts.manage_partition_retention --output "logs\partition_retention_latest.json" %* >> "logs\partition_retention.log" 2>&1
exit /b %ERRORLEVEL%
