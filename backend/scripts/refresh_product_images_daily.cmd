@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start refresh_product_images >> "logs\refresh_product_images.log"
"D:\python\python.exe" -m scripts.refresh_product_images >> "logs\refresh_product_images.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end refresh_product_images errorlevel=%EXIT_CODE% >> "logs\refresh_product_images.log"

endlocal & exit /b %EXIT_CODE%
