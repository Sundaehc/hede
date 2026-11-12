@echo off
setlocal

rem Compatibility entry: web-maintained archives no longer use external imports.
call "%~dp0sync_products_and_copywriting_daily.cmd"
exit /b %ERRORLEVEL%
