@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
call .venv\Scripts\activate.bat
start "" http://localhost:8000
python -m uvicorn app.main:app --reload
pause
