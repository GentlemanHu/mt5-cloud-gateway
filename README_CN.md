# MetaTrader 5 云网关 & 多协议 MCP 服务器

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![MetaTrader 5](https://img.shields.io/badge/MetaTrader-5-orange.svg)](https://www.metatrader5.com/)
[![MCP Server](https://img.shields.io/badge/MCP-Server%20Ready-purple.svg)](https://modelcontextprotocol.io/)
[![Cloudflare Tunnel](https://img.shields.io/badge/Cloudflare-Tunnel%20Ready-F38020.svg)](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/GentlemanHu/mt5-cloud-gateway/pulls)

**专为 AI 大模型、量化交易智能体与云端监控打造的生产级 MetaTrader 5 HTTP REST、WebSocket、SSE 与模型上下文协议 (MCP) 统一网关。**

[English](README.md) • [简体中文](README_CN.md)

</div>

---

## 🌟 项目亮点

**MetaTrader 5 Cloud Gateway** 将传统的 Windows 桌面版 MetaTrader 5 终端无缝接入现代 Web 与 AI 生态系统，具备以下核心能力：

- **13 项原生 MCP 工具**：深度实现 Anthropic / Model Context Protocol (MCP 2024-11-05 标准)，提供 **Streamable HTTP**、**Server-Sent Events (SSE)** 以及 **便携式 Stdio 桥接器** 三种传输通道。
- **工业级动态多维 K 线 (OHLCV) 引擎**：支持 MT5 全量 21 种时间周期（M1 到 MN1），单次支持超大批量（10,000+ 柱）并发检索，支持时间范围筛选、偏移分页，并实时识别最新未收盘形成中 K 线（`is_closed: false`）与 SSE 实时推流（`GET /rates/stream`）。
- **双层解耦安全架构**：管理面板主密码（`HttpOnly` 会话 Cookie）与外部调用 Bearer API 令牌（`mt5_live_...`）彻底解耦，面板内建令牌生命周期管理中心（创建、重置、吊销、统计），未登录页面零敏感信息泄露。
- **可选自动化 Cloudflare 隧道 / 纯本地双模式**：配置 Cloudflare 隧道 Token 即可免公网 IP、免端口映射获得全球固定安全 HTTPS 域名；未配置则自动以纯本地/局域网模式无缝运行。
- **人类与大模型双重友好文档**：内置交互式开发者文档 (`/docs`)、OpenAPI 3.1.0 标准机读规范 (`/openapi.json`) 以及针对 LLM 优化的上下文清单 (`/llms.txt`)。

---

## 🏗️ 架构设计

```
                                  +---------------------------------------+
                                  |   AI Agent (Claude / Cursor / GPT)    |
                                  |   Webhook / 量化量化系统 / 交易员面板 |
                                  +-------------------+-------------------+
                                                      |
                             [Streamable HTTP / SSE / WebSocket / Stdio]
                                                      |
                  +-----------------------------------+-----------------------------------+
                  |                                                                       |
      [Cloudflare 隧道] (可选自动化)                                           [本地 / 局域网直连]
   https://your-domain.com                                                   http://localhost:18812
                  |                                                                       |
                  +-----------------------------------+-----------------------------------+
                                                      |
                                       +--------------v--------------+
                                       |      MT5 Cloud Gateway      |
                                       |  - 令牌全生命周期与安全审计 |
                                       |  - 13 项标准 MCP 工具调度器 |
                                       |  - 动态多维 K 线 (OHLCV)引擎|
                                       |  - 内存实时行情推送中心     |
                                       +--------------+--------------+
                                                      | 命名管道 IPC (原生低延迟)
                                       +--------------v--------------+
                                       |      MetaTrader 5 客户端    |
                                       |  (terminal64.exe / Windows) |
                                       +--------------+--------------+
                                                      |
                                       +--------------v--------------+
                                       |      经纪商真实/模拟服务器  |
                                       +-----------------------------+
```

---

## 🚀 快速开始

### 1. 运行环境要求
- Windows 10/11 或 Windows Server（或 Parallels Desktop / VMware / Proxmox 内的 Windows 虚拟机）。
- 已安装 MetaTrader 5 桌面客户端并成功登录交易账户。
- Python 3.10 或更高版本（已加入系统环境变量 PATH）。

### 2. 获取代码与初始化配置
```bash
git clone https://github.com/GentlemanHu/mt5-cloud-gateway.git
cd mt5-cloud-gateway

# 复制环境变量模板
cp .env.example .env
```

### 3. 配置 `.env`
编辑 `.env` 文件，按需配置：
```ini
# 服务监听地址与端口
MT5_HOST=0.0.0.0
MT5_HTTP_PORT=18812
MT5_WS_PORT=18813

# Web 控制台管理员主密码 (/ 或 /dashboard)
MT5_PANEL_PASSWORD=your_secure_password_here

# (可选) Cloudflare Tunnel Token，配置后自动开启外网安全域名穿透
CLOUDFLARE_TUNNEL_TOKEN=
```

### 4. 一键启动
- **Windows 一键运行**：直接双击运行 `start.bat`（自动检查 Python 环境、自动补齐依赖、自动处理隧道与启动服务）。
- **命令行启动**：
  ```bash
  pip install -r requirements.txt
  python mt5_server.py
  ```
- **配置开机自动启动服务**：以管理员身份运行 `install_service.bat`，即可在 Windows 计划任务中自动注册为自启动守护项。

---

## 🔌 模型上下文协议 (MCP) 接入指南

网关原生支持 Anthropic MCP 2024-11-05 协议规范，提供三种灵活连接模式：

### 1. Claude Desktop (原生 SSE 模式 - 强烈推荐)
无需在宿主机配置 Python 环境与路径，直接在 `claude_desktop_config.json` 中配置：
```json
{
  "mcpServers": {
    "mt5-gateway": {
      "url": "https://your-domain.com/mcp/sse?token=YOUR_BEARER_TOKEN"
    }
  }
}
```

### 2. Cursor / Windsurf / Claude Code (便携式 Stdio 桥接模式)
网关直接托管无依赖的便携式客户端脚本 `/mcp/client.py`，彻底消除对本地绝对路径的硬编码：
```bash
# 下载便携式脚本
curl -fsSL https://your-domain.com/mcp/client.py -o mt5_client.py

# 本地执行
python3 mt5_client.py --token "YOUR_BEARER_TOKEN" --url "https://your-domain.com"
```

在 Cursor (`~/.cursor/mcp.json`) 中配置示例：
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

### 3. Streamable HTTP 协议
向 `POST /mcp` 发送标准 JSON-RPC 2.0 报文：
```bash
curl -s -X POST "https://your-domain.com/mcp" \
  -H "Authorization: Bearer YOUR_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

---

## 🛠️ 内建 13 项 MCP 工具矩阵

| 工具标识 | 核心功能 | 主要入参 |
|:---|:---|:---|
| `mt5_get_status` | 查询终端运行状态、版本号及账户基本概况 | *(无)* |
| `mt5_get_account` | 获取账户净值、余额、杠杆、已用与可用保证金 | *(无)* |
| `mt5_get_tick` | 获取指定交易品种最新实时买卖报价（支持大小写与后缀模糊匹配） | `symbol` (必填) |
| `mt5_get_rates` | 多维 K 线数据检索（支持所有周期、范围切片、分页与未收盘实时柱） | `symbol`, `timeframe`, `count`, `start`, `start_time`, `end_time` |
| `mt5_list_symbols` | 获取经纪商支持的交易品种列表，支持按关键词筛选 | `group` (可选) |
| `mt5_get_symbol_info` | 查询品种合约规格参数（点差、最小手数、点值、隔夜利息等） | `symbol` (必填) |
| `mt5_get_positions` | 查询当前全部未平仓持仓列表（单号、方向、开仓价、浮动盈亏） | *(无)* |
| `mt5_get_orders` | 查询未触发的挂单列表 | *(无)* |
| `mt5_order_send` | 提交市价或挂单买卖指令，支持止损、止盈与注释标签 | `symbol`, `action` ("buy"/"sell"), `volume`, `sl`, `tp` |
| `mt5_position_close` | 根据订单号 (ticket) 进行平仓 | `ticket` (必填) |
| `mt5_restart_terminal` | 安全重启 Windows 宿主机内的 MetaTrader 5 桌面终端进程 | *(无)* |
| `mt5_restart_gateway` | 重启网关服务后台进程与内存报价分发池 | *(无)* |
| `mt5_get_logs` | 获取网关最新运行与交互审计日志 | `lines` (默认 50) |

---

## 📊 动态多维 K 线 (OHLCV) 引擎

### 支持的全部周期
`M1`, `M2`, `M3`, `M4`, `M5`, `M6`, `M10`, `M12`, `M15`, `M20`, `M30`, `H1`, `H2`, `H3`, `H4`, `H6`, `H8`, `H12`, `D1`, `W1`, `MN1`（同时兼容 `1m`, `5m`, `15m`, `1h`, `4h`, `1d` 等缩写别名）。

### 调用示例
```bash
# 1. 基础数量查询（默认包含当前跳动中的未收盘柱）
curl -s -H "Authorization: Bearer <TOKEN>" "http://localhost:18812/rates?symbol=XAUUSD&timeframe=M1&count=100"

# 2. 深度历史大批量拉取（如 10,000 根）与翻页偏移
curl -s -H "Authorization: Bearer <TOKEN>" "http://localhost:18812/rates?symbol=XAUUSD&timeframe=H1&count=10000&start=500"

# 3. 确定历史时间段区间切片
curl -s -H "Authorization: Bearer <TOKEN>" "http://localhost:18812/rates?symbol=BTCUSD&timeframe=D1&start_time=2026-01-01&end_time=2026-10-09"

# 4. SSE 动态 K 线流长连接订阅（毫秒级推送 kline_update, kline_closed, kline_open）
curl -N "http://localhost:18812/rates/stream?symbol=XAUUSD&timeframe=M1&token=<TOKEN>"
```

---

## 📖 公开服务与文档入口

- **Web 控制台**：`http://localhost:18812/`（受主密码保护）
- **交互式开发者接口文档**：`http://localhost:18812/docs`
- **大模型机读清单 (LLMs.txt)**：`http://localhost:18812/llms.txt`
- **OpenAPI 3.1.0 标准契约**：`http://localhost:18812/openapi.json`
- **便携式客户端脚本**：`http://localhost:18812/mcp/client.py`

---

## 🔒 安全与最佳实践

1. **面板密码与 API 令牌独立解耦**：面板主密码仅用于解锁网页端，任何外部 API、量化机器人或 MCP 均使用独立的 Bearer Token。
2. **多凭证生命周期**：可在控制台随时重置 (Regenerate)、撤销 (Revoke) 任意令牌，且实时生效。
3. **消除本地路径硬编码**：便携客户端下载接口 (`/mcp/client.py`) 完全自包含，不暴露任何开发机内部文件路径。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 协议开源。
作者：[Gentleman.Hu](https://github.com/GentlemanHu)。欢迎 Star 与提交 Pull Request！
