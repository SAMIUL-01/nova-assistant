@echo off
title Nova - Stop
echo.
echo  Stopping Nova...
echo.

set "FOUND="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
    if not errorlevel 1 (
        echo  [OK] Stopped Nova ^(process %%a^).
        set "FOUND=1"
    )
)

if not defined FOUND (
    echo  Nova does not appear to be running.
)

echo.
timeout /t 3 >nul
