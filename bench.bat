@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
call .venv\Scripts\activate.bat
if not exist logs mkdir logs
python -u bench\run_bench.py > logs\bench.log 2>&1
type logs\bench.log
echo.
echo Results saved. Open http://localhost:8000/benchmark (run.bat must be running).
start "" http://localhost:8000/benchmark
pause
