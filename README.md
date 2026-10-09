# MetaTrader 5 Cloud Gateway & Multi-Transport MCP Server

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![MetaTrader 5](https://img.shields.io/badge/MetaTrader-5-orange.svg)](https://www.metatrader5.com/)
[![MCP Protocol](https://img.shields.io/badge/MCP-2024--11--05-purple.svg)](https://modelcontextprotocol.io/)
[![Cloudflare Tunnel](https://img.shields.io/badge/Cloudflare-Tunnel%20Ready-F38020.svg)](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/GentlemanHu/mt5-cloud-gateway/pulls)

**Production-grade MetaTrader 5 HTTP REST, WebSocket, SSE & Model Context Protocol (MCP) Gateway for AI Agents, Algorithmic Trading and Cloud Monitoring.**

[English](README.md) • [简体中文](README_CN.md)

</div>

---

## 🌟 Overview

**MetaTrader 5 Cloud Gateway** bridges MetaTrader 5 (MT5) with the modern web and AI ecosystem. It turns any native Windows MT5 instance into a high-throughput, cloud-ready trading gateway with:

- **13 Built-in MCP Tools**: Native implementation of the Anthropic/Model Context Protocol (MCP 2024-11-05 specification) supporting **Streamable HTTP**, **Server-Sent Events (SSE)**, and **Portable Stdio** client transports.
- **Dynamic Multi-Dimensional K-Line (OHLCV) Engine**: Query any timeframe (M1 to MN1), pull deep historical sequences (10,000+ bars), perform time-range slices or offset pagination, and stream real-time forming candle updates with sub-millisecond latency.
- **Two-Tier Decoupled Security Model**: Web dashboard protected by a global master password (`HttpOnly` session cookie) completely decoupled from external Bearer API tokens (`mt5_live_...`), with token lifecycle management (create, regenerate, revoke, delete).
- **Zero-Config Cloudflare Tunnel or Pure Local Mode**: Run with Cloudflare Tunnel for secure global HTTPS without open ports or public IPv4, or run in pure local/LAN mode.
- **Full Developer & AI Documentation**: Interactive developer portal (`/docs`), OpenAPI 3.1.0 specification (`/openapi.json`), and LLM-optimized machine context manifest (`/llms.txt`).

---

## 🏗️ Architecture

```
                                  +---------------------------------------+
                                  |   AI Agents (Claude / Cursor / etc.)  |
                                  |   Webhooks / Custom Algo Bots / Users |
                                  +-------------------+-------------------+
                                                      |
                             [Streamable HTTP / SSE / WebSocket / Stdio]
                                                      |
                  +-----------------------------------+-----------------------------------+
                  |                                                                       |
     [Cloudflare Tunnel] (Optional)                                            [Local / LAN Direct]
  https://your-domain.com                                                    http://localhost:18812
                  |                                                                       |
                  +-----------------------------------+-----------------------------------+
                                                      |
                                       +--------------v--------------+
                                       |      MT5 Cloud Gateway      |
                                       |  - Auth & Token Lifecycle   |
                                       |  - MCP Dispatcher (13 Tools)|
                                       |  - Dynamic K-Line Engine    |
                                       |  - Quotation Hub (SSE & WS) |
                                       |  - Audit Log & Connections  |
                                       +--------------+--------------+
                                                      | Named Pipe IPC
                                       +--------------v--------------+
                                       |      MetaTrader 5 Client    |
                                       |  (terminal64.exe / Windows) |
                                       +--------------+--------------+
                                                      |
                                       +--------------v--------------+
                                       |      Broker Trading Server  |
                                       +-----------------------------+
```

---

## 🚀 Quick Start

### 1. Requirements
- Windows 10/11 or Windows Server (or Windows VM inside Parallels Desktop / VMware / Proxmox).
- MetaTrader 5 desktop client installed and logged in to your broker account.
- Python 3.10+ installed and added to `PATH`.

### 2. Clone and Setup
```bash
git clone https://github.com/GentlemanHu/mt5-cloud-gateway.git
cd mt5-cloud-gateway

# Copy environment configuration
cp .env.example .env
```

### 3. Configure `.env`
Edit `.env` to customize your preferences:
```ini
# Gateway listen address & port
MT5_HOST=0.0.0.0
MT5_HTTP_PORT=18812
MT5_WS_PORT=18813

# Master password for the Web Dashboard (/ or /dashboard)
MT5_PANEL_PASSWORD=your_secure_password_here

# (Optional) Cloudflare Tunnel Token for public access without public IP
CLOUDFLARE_TUNNEL_TOKEN=
```

### 4. Launch
- **Windows (One-Click)**: Double-click `start.bat` (automatically installs dependencies, checks configuration, and launches).
- **Manual Launch**:
  ```bash
  pip install -r requirements.txt
  python mt5_server.py
  ```
- **Windows Auto-Start on Boot**: Run `install_service.bat` as Administrator to register `RunMT5Gateway` in Windows Task Scheduler.

---

## 🔌 Model Context Protocol (MCP) Integration

The gateway natively implements the MCP 2024-11-05 specification across three transports:

### 1. Claude Desktop (Native SSE - Recommended)
Add this to your `claude_desktop_config.json` (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS or `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "mt5-gateway": {
      "url": "https://your-domain.com/mcp/sse?token=YOUR_BEARER_TOKEN"
    }
  }
}
```

### 2. Cursor / Windsurf / Claude Code (Portable Stdio Bridge)
The gateway serves a portable, dependency-free Stdio-to-HTTP bridge at `/mcp/client.py`:

```bash
# Download client script
curl -fsSL https://your-domain.com/mcp/client.py -o mt5_client.py

# Run with token
python3 mt5_client.py --token "YOUR_BEARER_TOKEN" --url "https://your-domain.com"
```

Or configure directly in Cursor (`~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "mt5-gateway": {
      "command": "python3",
      "args": ["mt5_client.py", "--token", "YOUR_BEARER_TOKEN", "--url", "https://your-domain.com"]
    }
  }
}
```

### 3. Streamable HTTP Protocol
Send standard JSON-RPC 2.0 requests directly to `POST /mcp`:
```bash
curl -s -X POST "https://your-domain.com/mcp" \
  -H "Authorization: Bearer YOUR_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

---

## 🛠️ Built-in MCP Tools (13 Tools)

| Tool Name | Description | Key Arguments |
|:---|:---|:---|
| `mt5_get_status` | Get MT5 terminal connection status, build version, and account summary. | *(None)* |
| `mt5_get_account` | Retrieve account equity, balance, leverage, margin, and free margin. | *(None)* |
| `mt5_get_tick` | Fetch real-time Bid/Ask tick prices with fuzzy symbol resolution. | `symbol` (required) |
| `mt5_get_rates` | Advanced OHLCV candle query (all timeframes, range, offset, forming bar). | `symbol`, `timeframe`, `count`, `start`, `start_time`, `end_time` |
| `mt5_list_symbols` | List available instruments, optionally filtered by keyword or group. | `group` (optional) |
| `mt5_get_symbol_info` | Detailed contract specifications (spread, min lot, point value, margin). | `symbol` (required) |
| `mt5_get_positions` | Retrieve all open market positions (tickets, open prices, PnL). | *(None)* |
| `mt5_get_orders` | List pending orders. | *(None)* |
| `mt5_order_send` | Submit market execution or pending orders with SL/TP and comments. | `symbol`, `action` ("buy"/"sell"), `volume`, `sl`, `tp` |
| `mt5_position_close` | Close an existing position by its ticket ID. | `ticket` (required) |
| `mt5_restart_terminal` | Restart the MetaTrader 5 terminal process safely on the host. | *(None)* |
| `mt5_restart_gateway` | Reload the gateway server and quotation memory hub. | *(None)* |
| `mt5_get_logs` | Retrieve recent gateway execution and debug logs. | `lines` (default 50) |

---

## 📊 Dynamic K-Line (OHLCV) Engine

### Supported Timeframes
`M1`, `M2`, `M3`, `M4`, `M5`, `M6`, `M10`, `M12`, `M15`, `M20`, `M30`, `H1`, `H2`, `H3`, `H4`, `H6`, `H8`, `H12`, `D1`, `W1`, `MN1` (aliases like `1m`, `5m`, `15m`, `1h`, `4h`, `1d` supported).

### Query Examples
```bash
# 1. Standard count query (includes live forming candle by default)
curl -s -H "Authorization: Bearer <TOKEN>" "http://localhost:18812/rates?symbol=XAUUSD&timeframe=M1&count=100"

# 2. Large historical batch (e.g. 10,000 bars) with offset pagination
curl -s -H "Authorization: Bearer <TOKEN>" "http://localhost:18812/rates?symbol=XAUUSD&timeframe=H1&count=10000&start=500"

# 3. Exact date-range query
curl -s -H "Authorization: Bearer <TOKEN>" "http://localhost:18812/rates?symbol=BTCUSD&timeframe=D1&start_time=2026-01-01&end_time=2026-10-09"

# 4. Real-time K-Line SSE stream (emits kline_update, kline_closed, kline_open)
curl -N "http://localhost:18812/rates/stream?symbol=XAUUSD&timeframe=M1&token=<TOKEN>"
```

---

## 📖 Public Endpoints & Documentation

- **Web Dashboard**: `http://localhost:18812/` (Protected by master password)
- **Interactive API Docs**: `http://localhost:18812/docs`
- **LLM Manifest**: `http://localhost:18812/llms.txt`
- **OpenAPI 3.1.0 Schema**: `http://localhost:18812/openapi.json`
- **Portable Stdio Client**: `http://localhost:18812/mcp/client.py`

---

## 🔒 Security Best Practices

1. **Master Password vs API Tokens**: The master panel password only unlocks the web console. API calls and MCP clients must use separate Bearer tokens.
2. **Token Revocation**: Any token can be revoked or deleted instantly from the dashboard, terminating external access immediately.
3. **No Private Path Leakage**: The client bridge download (`/mcp/client.py`) is completely self-contained with no local machine paths.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
Created with passion by [Gentleman.Hu](https://github.com/GentlemanHu).
