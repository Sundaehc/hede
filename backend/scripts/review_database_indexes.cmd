@echo off
setlocal
cd /d "%~dp0.."
if not exist "logs" mkdir "logs"

"D:\python\python.exe" -m scripts.review_database_indexes --output "logs\index_review_latest.json" %* >> "logs\index_review.log" 2>&1
exit /b %ERRORLEVEL%
