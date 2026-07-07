@echo off
cd /d "%~dp0\.."
python -m scripts.import_aftersale_returns_daily %*
