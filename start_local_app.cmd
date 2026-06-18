@echo off
setlocal
cd /d "%~dp0"

python scripts\run_local_app.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Startup failed. Review the message above.
  pause
)

exit /b %EXIT_CODE%
