@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo CineForge virtual environment is missing: %CD%\.venv
  echo Create it and install dependencies before starting CineForge.
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\start_cineforge.py" %*
set "cineforge_exit_code=%ERRORLEVEL%"
if not "%cineforge_exit_code%"=="0" (
  echo.
  echo CineForge startup failed with exit code %cineforge_exit_code%.
  echo Review the message above or logs under storage\runtime\supervisor\logs.
  if "%~1"=="" pause
)
exit /b %cineforge_exit_code%
