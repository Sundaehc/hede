@echo off
setlocal

cd /d "%~dp0\.."
if not exist "logs" mkdir "logs"

echo [%date% %time%] start refresh_supplier_ratings >> "logs\refresh_supplier_ratings.log"
"D:\python\python.exe" -m scripts.refresh_supplier_ratings %* >> "logs\refresh_supplier_ratings.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end refresh_supplier_ratings errorlevel=%EXIT_CODE% >> "logs\refresh_supplier_ratings.log"

endlocal & exit /b %EXIT_CODE%
