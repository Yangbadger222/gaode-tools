@echo off
setlocal
cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\launch_easy.py" %*
) else if exist "%WINDIR%\py.exe" (
  "%WINDIR%\py.exe" -3.12 "scripts\launch_easy.py" %*
) else (
  py -3.12 "scripts\launch_easy.py" %*
)
if errorlevel 1 (
  echo.
  echo The annotation tool exited with an error. Keep this window open and send the message above to the maintainer.
  pause
)
endlocal
