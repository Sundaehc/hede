@echo off
setlocal
cd /d "%~dp0.."
set "PYTHON=D:\python\python.exe"
"%PYTHON%" -m scripts.run_scheduled_task --task-name "HedeCheckInventoryProductLinksDaily" --log-file "logs\check_inventory_product_links.log" -- "%PYTHON%" -m scripts.check_inventory_product_links %*
exit /b %ERRORLEVEL%
