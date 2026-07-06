@echo off
setlocal
title OW Strategiser
cd /d "%~dp0ow_counterpick"

REM --- find a working Python ---
set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
  if exist "C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe" (
    set "PY=C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe"
  ) else (
    echo.
    echo Could not find Python on this PC.
    echo Install Python 3 from https://www.python.org/downloads/ and run this again.
    echo.
    pause
    exit /b 1
  )
)

echo Starting OW Strategiser server...
start "OW Strategiser Server" /min "%PY%" server.py

REM give the server a moment to come up, then open the browser
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765

echo.
echo The app is opening in your browser at http://127.0.0.1:8765
echo A minimized "OW Strategiser Server" window is running the app.
echo Close that window (or press any key in it) to stop the app.
timeout /t 4 /nobreak >nul
exit /b 0
