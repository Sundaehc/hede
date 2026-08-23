@echo off
setlocal
cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedePartitionRetentionReview" --log-file "logs\partition_retention.log" -- "D:\python\python.exe" -m scripts.manage_partition_retention --output "logs\partition_retention_latest.json" %*
exit /b %ERRORLEVEL%
