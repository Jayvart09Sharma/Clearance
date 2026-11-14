@echo off
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 (
  echo Git is not installed. Get it from https://git-scm.com/download/win , then run push.bat again.
  pause
  exit /b 1
)
set REPO=https://github.com/Jayvart09Sharma/Clearance.git
if not exist .git git init -b main
git add -A
git status --short | findstr /i "\.env$" && (echo STOP: .env would be committed. & pause & exit /b 1)
git -c user.name="Clearance Team" -c user.email="team@clearance.local" commit -m "Clearance: Drex expense approval + benchmark (Drexathon 2026)"
git branch -M main
git remote remove origin >nul 2>nul
git remote add origin %REPO%
git push -u origin main
if errorlevel 1 (
  echo Remote already has files ^(e.g. a README^). Merging them in, keeping ours...
  git -c user.name="Clearance Team" -c user.email="team@clearance.local" pull origin main --allow-unrelated-histories --no-edit -X ours
  git push -u origin main
)
echo.
echo Done. Open %REPO% in your browser to check.
pause
