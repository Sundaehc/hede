@echo off
setlocal
cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeDatabaseMissingDataReview" --log-file "logs\missing_data_review.log" -- "D:\python\python.exe" -m scripts.review_missing_data %*
exit /b %ERRORLEVEL%