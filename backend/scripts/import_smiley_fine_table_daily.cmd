@echo off
setlocal
cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeImportSmileyFineTableDaily" --log-file "logs\import_smiley_fine_table.log" -- "D:\python\python.exe" -m scripts.import_smiley_fine_table --replace
exit /b %ERRORLEVEL%
