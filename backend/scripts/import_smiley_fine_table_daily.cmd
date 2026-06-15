@echo off
setlocal
cd /d "%~dp0.."
echo [%date% %time%] start import_smiley_fine_table >> "logs\import_smiley_fine_table.log"
"D:\python\python.exe" -m scripts.import_smiley_fine_table --replace >> "logs\import_smiley_fine_table.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] end import_smiley_fine_table errorlevel=%EXIT_CODE% >> "logs\import_smiley_fine_table.log"
exit /b %EXIT_CODE%
