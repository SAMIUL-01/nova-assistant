@echo off
title Nova - Doctor
cd /d "%~dp0"

if not exist "app\main.py" (
    if exist "nova\app\main.py" cd "nova"
)

echo.
echo  Checking your setup...
echo.

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) else (
    echo  [!] No virtual environment found - run SETUP.bat first.
    echo.
)

python check_setup.py

echo.
echo  --------------------------------------------------------------
echo   Still stuck? Copy EVERYTHING above and send it for help.
echo  --------------------------------------------------------------
echo.
pause
