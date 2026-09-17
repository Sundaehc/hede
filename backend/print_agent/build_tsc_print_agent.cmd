@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo ??? backend\.venv????????????
  pause
  exit /b 1
)

set "PACKAGE_DIR=dist\HedePrintAgentService"
if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
if not exist "build\spec" mkdir "build\spec"
if not exist "%PACKAGE_DIR%" mkdir "%PACKAGE_DIR%"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --noconsole --name HedePrintAgent --specpath build\spec --distpath "%PACKAGE_DIR%" --workpath build\HedePrintAgent print_agent\tsc_print_agent.py
if errorlevel 1 (
  echo.
  echo ??????????uv pip install pyinstaller
  pause
  exit /b 1
)

copy /y "print_agent\HedePrintAgent.config.json" "%PACKAGE_DIR%\HedePrintAgent.config.json" >nul
copy /y "print_agent\install_windows_service.cmd" "%PACKAGE_DIR%\Install-Service.cmd" >nul
copy /y "print_agent\install_windows_service.ps1" "%PACKAGE_DIR%\install_windows_service.ps1" >nul
copy /y "print_agent\uninstall_windows_service.cmd" "%PACKAGE_DIR%\Uninstall-Service.cmd" >nul
copy /y "print_agent\uninstall_windows_service.ps1" "%PACKAGE_DIR%\uninstall_windows_service.ps1" >nul
copy /y "print_agent\restart_windows_service.cmd" "%PACKAGE_DIR%\Restart-Service.cmd" >nul
copy /y "print_agent\restart_windows_service.ps1" "%PACKAGE_DIR%\restart_windows_service.ps1" >nul
copy /y "print_agent\check_windows_service.cmd" "%PACKAGE_DIR%\Check-Service.cmd" >nul
copy /y "print_agent\check_windows_service.ps1" "%PACKAGE_DIR%\check_windows_service.ps1" >nul
copy /y "print_agent\README.md" "%PACKAGE_DIR%\????.md" >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%PACKAGE_DIR%\*' -DestinationPath 'dist\HedePrintAgentService.zip' -Force"

echo.
echo ????backend\dist\HedePrintAgentService.zip
pause
