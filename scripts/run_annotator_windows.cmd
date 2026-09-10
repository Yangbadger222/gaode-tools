@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Virtual environment not found.
  echo Run: powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "scripts\launch_annotator.py" --language zh %*
if errorlevel 1 (
  echo.
  echo The annotation tool exited with an error. Keep this window open and send the message above to the maintainer.
  pause
)
endlocal
