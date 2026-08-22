@echo off
setlocal EnableDelayedExpansion
title Nova - Setup
cd /d "%~dp0"

echo.
echo  ==============================================================
echo    NOVA  -  ONE TIME SETUP
echo  ==============================================================
echo.
echo  This does everything for you:
echo    1. checks Python
echo    2. creates the virtual environment
echo    3. installs all packages
echo    4. sets up your API key
echo    5. tests that it works
echo.
echo  Run this ONCE. After that, use START.bat
echo.
pause
echo.

REM ---------------------------------------------------------------- 0. doubled folder
if not exist "app\main.py" (
    if exist "nova\app\main.py" (
        echo  [!] The zip was extracted into a doubled folder.
        echo      Moving into: %CD%\nova
        cd "nova"
    )
)
if not exist "app\main.py" (
    echo.
    echo  [ERROR] Project files were not found in this folder.
    echo          SETUP.bat must sit next to the "app" folder.
    echo          Extract the zip again and try once more.
    echo.
    pause
    exit /b 1
)

REM ---------------------------------------------------------------- 1. Python
echo  [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python is not installed, or not on your PATH.
    echo.
    echo    1. Download Python 3.12 from https://www.python.org/downloads/
    echo    2. During install, TICK the box "Add python.exe to PATH"
    echo    3. Close this window, open a NEW one, and run SETUP.bat again
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo        Python !PYVER! found.

REM ---------------------------------------------------------------- 2. venv
echo.
echo  [2/5] Creating the virtual environment...
if exist "venv\Scripts\python.exe" (
    echo        Already exists - reusing it.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo  [ERROR] Could not create the virtual environment.
        echo          Try running this file as Administrator, or move the
        echo          project to a simple path such as C:\nova
        echo.
        pause
        exit /b 1
    )
    echo        Created.
)

call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo  [ERROR] Could not activate the virtual environment.
    pause
    exit /b 1
)

REM ---------------------------------------------------------------- 3. packages
echo.
echo  [3/5] Installing packages ^(this can take 1-3 minutes^)...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Installing packages failed.
    echo          Check your internet connection and run SETUP.bat again.
    echo.
    pause
    exit /b 1
)
echo        All packages installed.

REM ---- 3b. app icons (PNG/ICO are generated, not stored in git) -----------
if not exist "static\icons\nova-192.png" (
    echo        Generating app icons...
    python tools\make_icons.py >nul 2>&1
    if errorlevel 1 (
        echo        [note] Icon generation skipped - Nova still works fine.
    ) else (
        echo        Icons created.
    )
)

REM ---------------------------------------------------------------- 4. .env
echo.
echo  [4/5] Setting up your configuration...

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo        Created .env from the template.
) else (
    echo        Existing .env found - your key is kept.
    findstr /c:"YOUR_API_KEY_HERE" ".env" >nul 2>&1
    if errorlevel 1 (
        echo        API key already set. Skipping.
        goto :env_done
    )
)

echo.
echo  --------------------------------------------------------------
echo    PASTE YOUR OPENROUTER API KEY
echo.
echo    Get a free one at:  https://openrouter.ai/keys
echo    ^(right-click to paste, then press Enter^)
echo.
echo    Or just press Enter to skip and use TEST MODE with fake
echo    replies - you can add the real key later.
echo  --------------------------------------------------------------
echo.
set "APIKEY="
set /p APIKEY=  Your key: 

if "!APIKEY!"=="" (
    echo.
    echo        No key entered - turning ON test mode ^(fake replies^).
    powershell -NoProfile -Command "(Get-Content '.env') -replace '^AI_OFFLINE_MOCK=.*','AI_OFFLINE_MOCK=1' | Set-Content '.env'"
) else (
    powershell -NoProfile -Command "(Get-Content '.env') -replace '^OPENROUTER_API_KEY=.*','OPENROUTER_API_KEY=!APIKEY!' | Set-Content '.env'"
    powershell -NoProfile -Command "(Get-Content '.env') -replace '^AI_OFFLINE_MOCK=.*','AI_OFFLINE_MOCK=0' | Set-Content '.env'"
    echo.
    echo        Key saved to .env ^(this file is never uploaded to GitHub^).
)

:env_done

REM ---------------------------------------------------------------- 5. verify
echo.
echo  [5/5] Checking everything...
echo.
python check_setup.py
if errorlevel 1 (
    echo.
    echo  ==============================================================
    echo    SETUP STOPPED - see the FIX lines above.
    echo    Fix them, then run SETUP.bat again.
    echo  ==============================================================
    echo.
    pause
    exit /b 1
)

echo.
echo  Running the test suite to be sure...
python -m pytest -q
echo.
echo  ==============================================================
echo    SETUP COMPLETE
echo  ==============================================================
echo.
echo    Now double-click:   START.bat
echo.
echo    If anything ever breaks, double-click:  DOCTOR.bat
echo.
pause
