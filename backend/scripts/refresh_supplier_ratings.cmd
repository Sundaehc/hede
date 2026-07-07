@echo off
cd /d "%~dp0\.."
python -m scripts.refresh_supplier_ratings %*
