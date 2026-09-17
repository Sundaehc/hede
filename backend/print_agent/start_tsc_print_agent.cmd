@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

if not defined TSC_PRINTER_NAME set "TSC_PRINTER_NAME=TSCTTP-244 Pro"
if not defined TSC_PRINT_AGENT_PORT set "TSC_PRINT_AGENT_PORT=18120"
if not defined TSC_LABEL_GAP_MM set "TSC_LABEL_GAP_MM=2"
if not defined TSC_PRINT_DIRECTION set "TSC_PRINT_DIRECTION=1"
if not defined HEDE_PRINT_ALLOWED_ORIGINS set "HEDE_PRINT_ALLOWED_ORIGINS=https://platform.hedespace.com,http://127.0.0.1:3001,http://localhost:3001"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m print_agent.tsc_print_agent
) else (
  py -3 -m print_agent.tsc_print_agent
)

echo.
echo Hede 打印服务已退出。请查看上方错误信息。
pause
