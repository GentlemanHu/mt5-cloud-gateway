@echo off
setlocal
title MetaTrader 5 Cloud Gateway - Windows Auto-Start Installer

echo =====================================================================
echo    Install MetaTrader 5 Cloud Gateway as Auto-Start Scheduled Task
echo =====================================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE=python.exe"

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    for /f "delims=" %%I in ('where python') do set "PYTHON_EXE=%%I" & goto :found_python
)
:found_python

echo Creating Task: RunMT5Gateway
schtasks /create /tn "RunMT5Gateway" /tr "\"%PYTHON_EXE%\" -u \"%SCRIPT_DIR%mt5_server.py\"" /sc onlogon /rl highest /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] Auto-start task 'RunMT5Gateway' installed successfully!
    echo It will automatically run whenever user logs in.
    echo.
    echo To start it now: schtasks /run /tn "RunMT5Gateway"
    echo To stop it:     schtasks /end /tn "RunMT5Gateway"
    echo To remove it:   schtasks /delete /tn "RunMT5Gateway" /f
) else (
    echo.
    echo [ERROR] Failed to register task. Please run this script as Administrator.
)

pause
