@echo off
setlocal
cd /d "%~dp0.."
"D:\python\python.exe" -m scripts.run_scheduled_task --task-name "HedeDataGovernanceAudit" --log-file "logs\data_governance_audit.log" -- "D:\python\python.exe" -m scripts.audit_data_governance %*
exit /b %ERRORLEVEL%
