@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_windows_service.ps1"
pause
