@echo off
setlocal EnableDelayedExpansion
title Nova - Running
cd /d "%~dp0"

if not exist "app\main.py" (
    if exist "nova\app\main.py" cd "nova"
)

REM --- Has setup been run? ---
if not exist "venv\Scripts\activate.bat" (
    echo.
    echo  [!] Setup has not been run yet.
    echo      Please double-click SETUP.bat first.
    echo.
    pause
    exit /b 1
)

call "venv\Scripts\activate.bat"

if not exist ".env" (
    echo.
    echo  [!] The .env file is missing. Run SETUP.bat first.
    echo.
    pause
    exit /b 1
)

REM --- Find this PC's IP so the phone can connect ---
set "LANIP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    if not defined LANIP (
        set "LANIP=%%a"
        set "LANIP=!LANIP: =!"
    )
)

cls
echo.
echo  ==============================================================
echo    NOVA  -  starting
echo  ==============================================================
echo.
echo    On this PC:     http://127.0.0.1:8000
if defined LANIP (
echo    On your phone:  http://!LANIP!:8000
echo                    ^(same Wi-Fi; allow Python in the firewall^)
)
echo.
echo    Note: the microphone only works on http://127.0.0.1:8000
echo          or on a real https:// address. See DEPLOY.md.
echo.
echo    Press CTRL+C in this window to stop the server.
echo  ==============================================================
echo.

start "" http://127.0.0.1:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

echo.
echo  Server stopped.
pause
