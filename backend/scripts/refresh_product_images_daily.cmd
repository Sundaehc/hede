@echo off
setlocal

cd /d "%~dp0.."
"%~dp0..\.venv\Scripts\python.exe" -m scripts.run_scheduled_task --task-name "HedeRefreshProductImages" --log-file "logs\refresh_product_images.log" --skip-if-business-success "refresh_product_images_daily" -- "%~dp0..\.venv\Scripts\python.exe" -m scripts.refresh_product_images --daily
exit /b %ERRORLEVEL%
