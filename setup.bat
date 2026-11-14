@echo off
cd /d "%~dp0"
echo === Clearance setup ===
set PY=python
where py >nul 2>nul && set PY=py -3
%PY% --version
if errorlevel 1 (
  echo Python was not found. Install Python 3.12 from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then run this again.
  pause
  exit /b 1
)
if not exist .venv %PY% -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo Package install failed. Copy the error above and send it to Claude.
  pause
  exit /b 1
)
if not exist .env copy .env.example .env >nul
echo.
echo Setup done. Notepad will open .env: fill in NACE_API_KEY, DEEPINFRA_API_KEY and BASELINE_MODEL, save, close.
echo Then double-click run.bat
notepad .env
pause
