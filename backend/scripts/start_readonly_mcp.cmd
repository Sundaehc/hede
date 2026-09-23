@echo off
setlocal
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
if not exist ".venv-mcp\Scripts\python.exe" (
    echo MCP environment missing. See docs/MCP-readonly.md.
    exit /b 1
)
".venv-mcp\Scripts\python.exe" -m readonly_mcp.admin verify
if errorlevel 1 exit /b 1
".venv-mcp\Scripts\python.exe" -m readonly_mcp.server
exit /b %ERRORLEVEL%
