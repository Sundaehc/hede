@echo off
setlocal
cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "ReadSalesData-UpdateInventory" --log-file "logs\read_sales_data_inventory.log" --working-directory "E:\read_sales_data" -- "D:\python\python.exe" "E:\read_sales_data\main.py"
exit /b %ERRORLEVEL%
