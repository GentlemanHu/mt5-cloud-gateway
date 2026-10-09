#!/usr/bin/env bash
set -e

echo "====================================================================="
echo "   MetaTrader 5 Cloud Gateway & MCP Server Launcher"
echo "   Author: Gentleman.Hu | License: MIT"
echo "====================================================================="
echo ""

# 1. Check Python
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python 3.10+ is required but not found in PATH!"
    exit 1
fi

# 2. Check and initialize .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "[INFO] .env not found. Initializing from .env.example..."
        cp .env.example .env
        echo "[INFO] Created .env with default settings."
    fi
fi

# 3. Install dependencies
echo "[INFO] Checking Python dependencies..."
$PYTHON_CMD -m pip install -r requirements.txt -q || true

# 4. Check CLOUDFLARE_TUNNEL_TOKEN in .env
CF_TOKEN=""
if [ -f ".env" ]; then
    CF_TOKEN=$(grep -E "^CLOUDFLARE_TUNNEL_TOKEN=" .env | cut -d '=' -f2- | tr -d '"' | tr -d "'" || true)
fi

# 5. Optional Cloudflare Tunnel
if [ -n "$CF_TOKEN" ]; then
    echo "[INFO] CLOUDFLARE_TUNNEL_TOKEN detected!"
    if command -v cloudflared &>/dev/null; then
        echo "[INFO] Spawning background cloudflared tunnel..."
        cloudflared tunnel run --token "$CF_TOKEN" >/dev/null 2>&1 &
    else
        echo "[WARNING] 'cloudflared' command not found in PATH. Install cloudflared to use tunnel."
    fi
else
    echo "[INFO] No CLOUDFLARE_TUNNEL_TOKEN provided. Running in local / LAN mode."
fi

echo ""
echo "====================================================================="
echo "   Starting Gateway Server..."
echo "   Local Panel:  http://localhost:18812"
echo "   Local Docs:   http://localhost:18812/docs"
echo "   WebSocket:    ws://localhost:18813"
echo "====================================================================="
echo ""

exec $PYTHON_CMD mt5_server.py
