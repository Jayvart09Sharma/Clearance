@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
call .venv\Scripts\activate.bat
if not exist logs mkdir logs
python -u scripts\test_one.py > logs\test_drex.log 2>&1
type logs\test_drex.log
echo.
echo Saved to logs\test_drex.log
pause
