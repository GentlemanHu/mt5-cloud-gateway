@echo off
setlocal enabledelayedexpansion
title MetaTrader 5 Cloud Gateway & MCP Server

echo =====================================================================
echo    MetaTrader 5 Cloud Gateway ^& MCP Server Launcher
echo    Author: Gentleman.Hu ^| License: MIT
echo =====================================================================
echo.

:: 1. Check Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Python 3.10+ is required but not found in PATH!
        echo Please install Python from https://www.python.org/
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=py
    )
) else (
    set PYTHON_CMD=python
)

:: 2. Check and copy .env file
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] .env not found. Initializing from .env.example...
        copy ".env.example" ".env" >nul
        echo [INFO] Created .env with default settings.
    )
)

:: 3. Check and install dependencies
echo [INFO] Checking Python dependencies...
%PYTHON_CMD% -m pip install -r requirements.txt -q
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Pip install had issues. Attempting to proceed...
)

:: 4. Parse CLOUDFLARE_TUNNEL_TOKEN from .env
set CF_TOKEN=
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        set "KEY=%%A"
        set "VAL=%%B"
        if "!KEY!"=="CLOUDFLARE_TUNNEL_TOKEN" set "CF_TOKEN=!VAL!"
    )
)

:: 5. Handle Cloudflare Tunnel (Optional)
if not "%CF_TOKEN%"=="" (
    echo [INFO] CLOUDFLARE_TUNNEL_TOKEN detected!
    where cloudflared >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        if not exist "cloudflared.exe" (
            echo [INFO] Downloading cloudflared-windows-amd64.exe...
            curl.exe -fSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -o cloudflared.exe
        )
        set CF_BIN=cloudflared.exe
    ) else (
        set CF_BIN=cloudflared
    )

    if exist "!CF_BIN!" (
        echo [INFO] Starting Cloudflare Tunnel in background...
        start /b "" "!CF_BIN!" tunnel run --token "%CF_TOKEN%" >nul 2>&1
    ) else (
        echo [INFO] Starting Cloudflare Tunnel via system cloudflared...
        start /b "" cloudflared tunnel run --token "%CF_TOKEN%" >nul 2>&1
    )
) else (
    echo [INFO] No CLOUDFLARE_TUNNEL_TOKEN provided in .env.
    echo [INFO] Running in pure local / LAN network mode.
)

echo.
echo =====================================================================
echo    Starting Gateway Server...
echo    Local Panel:  http://localhost:18812
echo    Local Docs:   http://localhost:18812/docs
echo    WebSocket:    ws://localhost:18813
echo =====================================================================
echo.

%PYTHON_CMD% mt5_server.py
pause
