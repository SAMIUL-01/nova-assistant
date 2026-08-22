@echo off
setlocal EnableDelayedExpansion
title Nova - Create Shortcut
cd /d "%~dp0"

echo.
echo  ==============================================================
echo    NOVA  -  DESKTOP SHORTCUT
echo  ==============================================================
echo.

if not exist "Nova.vbs" (
    echo  [ERROR] Nova.vbs was not found next to this file.
    echo          Run this from inside the nova folder.
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo  [!] Nova is not set up yet. Please run SETUP.bat first.
    echo.
    pause
    exit /b 1
)

REM ---- build a tiny VBS that creates the shortcut --------------------------
set "MAKER=%TEMP%\nova_make_shortcut.vbs"
> "%MAKER%" echo Set sh = CreateObject("WScript.Shell"^)
>>"%MAKER%" echo desktop = sh.SpecialFolders("Desktop"^)
>>"%MAKER%" echo Set lnk = sh.CreateShortcut(desktop ^& "\Nova.lnk"^)
>>"%MAKER%" echo lnk.TargetPath = "%CD%\Nova.vbs"
>>"%MAKER%" echo lnk.WorkingDirectory = "%CD%"
>>"%MAKER%" echo lnk.IconLocation = "%CD%\static\icons\nova.ico"
>>"%MAKER%" echo lnk.Description = "Nova - your personal AI assistant"
>>"%MAKER%" echo lnk.Save

cscript //nologo "%MAKER%"
del "%MAKER%" >nul 2>&1

echo  [OK] Desktop shortcut created: Nova
echo.
echo  You can now start Nova by double-clicking the Nova icon
echo  on your Desktop. No black window, no commands.
echo.

REM ---- optional: start with Windows ---------------------------------------
echo  --------------------------------------------------------------
echo   Do you want Nova to start automatically when Windows starts?
echo   ^(It runs quietly in the background - nothing pops up.^)
echo  --------------------------------------------------------------
echo.
set "AUTO="
set /p AUTO=  Type Y for yes, or just press Enter to skip: 

if /i "!AUTO!"=="Y" (
    set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
    set "MAKER2=%TEMP%\nova_make_startup.vbs"
    > "!MAKER2!" echo Set sh = CreateObject("WScript.Shell"^)
    >>"!MAKER2!" echo Set lnk = sh.CreateShortcut("!STARTUP!\Nova.lnk"^)
    >>"!MAKER2!" echo lnk.TargetPath = "%CD%\Nova.vbs"
    >>"!MAKER2!" echo lnk.WorkingDirectory = "%CD%"
    >>"!MAKER2!" echo lnk.IconLocation = "%CD%\static\icons\nova.ico"
    >>"!MAKER2!" echo lnk.Save
    cscript //nologo "!MAKER2!"
    del "!MAKER2!" >nul 2>&1
    echo.
    echo  [OK] Nova will now start with Windows.
    echo       To undo: press Win+R, type  shell:startup  and delete Nova.
) else (
    echo.
    echo  Skipped. Nova will only start when you open it yourself.
)

echo.
echo  ==============================================================
echo    DONE
echo  ==============================================================
echo.
pause
