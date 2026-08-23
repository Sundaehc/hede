@echo off
setlocal
cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeDatabaseIndexReview" --log-file "logs\index_review.log" -- "D:\python\python.exe" -m scripts.review_database_indexes --output "logs\index_review_latest.json" %*
exit /b %ERRORLEVEL%
