@echo off
setlocal

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo [%date% %time%] start refresh_product_images >> "logs\refresh_product_images.log"
python -m scripts.refresh_product_images >> "logs\refresh_product_images.log" 2>&1
echo [%date% %time%] end refresh_product_images errorlevel=%errorlevel% >> "logs\refresh_product_images.log"

endlocal
