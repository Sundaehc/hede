@echo off
setlocal
cd /d "%~dp0.."
if not exist "logs" mkdir "logs"

echo [%date% %time%] start data_governance_audit >> "logs\data_governance_audit.log"
"D:\python\python.exe" -m scripts.audit_data_governance %* >> "logs\data_governance_audit.log" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] end data_governance_audit errorlevel=%EXIT_CODE% >> "logs\data_governance_audit.log"
exit /b %EXIT_CODE%
