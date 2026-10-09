import json
import MetaTrader5 as mt5
from datetime import datetime
import subprocess
import time
import os
import uuid
import queue
from mt5_kline_engine import fetch_rates_advanced, TIMEFRAME_MAP, TIMEFRAME_INFO

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "mt5-trading-gateway"
SERVER_VERSION = "1.0.0"

TOOLS_DEFINITIONS = [
    {
        "name": "mt5_get_status",
        "description": "获取 MetaTrader 5 交易终端与网关在线状态、版本号及基础连接信息",
        "inputSchema": { "type": "object", "properties": {} }
    },
    {
        "name": "mt5_get_account",
        "description": "获取当前登录交易账户资产概况，包括净值(equity)、余额(balance)、杠杆(leverage)、可用预付款与服务器信息",
        "inputSchema": { "type": "object", "properties": {} }
    },
    {
        "name": "mt5_get_tick",
        "description": "获取指定交易品种最新实时 Tick 盘口价格（支持智能大小写与后缀模糊解析，如 xauusd -> XAUUSDm）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": { "type": "string", "description": "交易品种代码，例如 XAUUSD, EURUSD, BTCUSD" }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "mt5_get_rates",
        "description": "获取指定品种的历史与实时动态 K 线(OHLCV)数据，支持任意周期(M1-MN1)、任意长度(可拉取10,000+根)、时间范围查询、偏移分页以及动态形成中 K 线标记(is_closed)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": { "type": "string", "description": "交易品种代码，例如 XAUUSD, EURUSDm, BTCUSDm" },
                "timeframe": { "type": "string", "description": "时间周期：M1, M2, M3, M4, M5, M6, M10, M12, M15, M20, M30, H1, H2, H3, H4, H6, H8, H12, D1, W1, MN1 (支持 1m, 5m, 1h, 1d 等别名)", "default": "M1" },
                "count": { "type": "integer", "description": "获取 K 线数量（默认 500，可支持 1000, 5000, 50000 等大批量请求）", "default": 500 },
                "start": { "type": "integer", "description": "起始位置偏移量（0 为最新，向前回溯分页）", "default": 0 },
                "start_time": { "type": "string", "description": "起始时间（ISO 8601 例如 2026-10-01T00:00:00，或 UNIX 时间戳）" },
                "end_time": { "type": "string", "description": "结束时间（ISO 8601 例如 2026-10-09T00:00:00，或 UNIX 时间戳）" },
                "include_forming": { "type": "boolean", "description": "是否包含当前正在跳动形成的最新未收盘 K 线 (is_closed: false)", "default": True }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "mt5_list_symbols",
        "description": "查询经纪商支持的交易品种列表，支持按关键词过滤",
        "inputSchema": {
            "type": "object",
            "properties": {
                "group": { "type": "string", "description": "过滤关键词或分组（可选）" }
            }
        }
    },
    {
        "name": "mt5_get_symbol_info",
        "description": "获取指定交易品种的详细规格参数（点差、最小变动价位、合约乘数、点值、隔夜利息等）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": { "type": "string", "description": "交易品种代码" }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "mt5_get_positions",
        "description": "获取当前未平仓交易持仓列表（持仓单号 ticket、品种、多空方向、手数、开仓价、浮动盈亏等）",
        "inputSchema": { "type": "object", "properties": {} }
    },
    {
        "name": "mt5_get_orders",
        "description": "获取当前挂单列表（未触发的挂单请求）",
        "inputSchema": { "type": "object", "properties": {} }
    },
    {
        "name": "mt5_order_send",
        "description": "向 MT5 提交市价或挂单交易指令",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": { "type": "string", "description": "交易品种，如 XAUUSDm" },
                "action": { "type": "string", "enum": ["buy", "sell"], "description": "交易买卖方向" },
                "volume": { "type": "number", "description": "交易手数（例如 0.01）", "default": 0.01 },
                "price": { "type": "number", "description": "指定成交价格（可选，留空则以最新市价成交）" },
                "sl": { "type": "number", "description": "止损价格 (Stop Loss)", "default": 0.0 },
                "tp": { "type": "number", "description": "止盈价格 (Take Profit)", "default": 0.0 },
                "comment": { "type": "string", "description": "订单备注标签", "default": "MCP Order" }
            },
            "required": ["symbol", "action", "volume"]
        }
    },
    {
        "name": "mt5_position_close",
        "description": "根据持仓单号 ticket 进行平仓操作",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket": { "type": "integer", "description": "持仓单号 (ticket)" }
            },
            "required": ["ticket"]
        }
    },
    {
        "name": "mt5_restart_terminal",
        "description": "在 Windows 11 交互桌面 (Session 1) 安全重启 MetaTrader 5 交易终端进程",
        "inputSchema": { "type": "object", "properties": {} }
    },
    {
        "name": "mt5_restart_gateway",
        "description": "重启 Windows 11 虚拟机内部的网关服务后台守护进程",
        "inputSchema": { "type": "object", "properties": {} }
    },
    {
        "name": "mt5_get_logs",
        "description": "获取 Windows 网关服务最新的运行与调试日志",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lines": { "type": "integer", "description": "获取最后 N 行日志", "default": 50 }
            }
        }
    }
]

TIMEFRAME_MAP = {
    'M1': mt5.TIMEFRAME_M1, 'M2': mt5.TIMEFRAME_M2, 'M3': mt5.TIMEFRAME_M3,
    'M4': mt5.TIMEFRAME_M4, 'M5': mt5.TIMEFRAME_M5, 'M6': mt5.TIMEFRAME_M6,
    'M10': mt5.TIMEFRAME_M10, 'M12': mt5.TIMEFRAME_M12, 'M15': mt5.TIMEFRAME_M15,
    'M20': mt5.TIMEFRAME_M20, 'M30': mt5.TIMEFRAME_M30, 'H1': mt5.TIMEFRAME_H1,
    'H2': mt5.TIMEFRAME_H2, 'H3': mt5.TIMEFRAME_H3, 'H4': mt5.TIMEFRAME_H4,
    'H6': mt5.TIMEFRAME_H6, 'H8': mt5.TIMEFRAME_H8, 'H12': mt5.TIMEFRAME_H12,
    'D1': mt5.TIMEFRAME_D1, 'W1': mt5.TIMEFRAME_W1, 'MN1': mt5.TIMEFRAME_MN1,
}

class McpDispatcher:
    def __init__(self, resolve_symbol_func, hub_instance=None):
        self.resolve_symbol = resolve_symbol_func
        self.hub = hub_instance
        self._sse_sessions = {} # session_id -> queue.Queue

    def create_sse_session(self):
        sid = uuid.uuid4().hex
        q = queue.Queue()
        self._sse_sessions[sid] = q
        return sid, q

    def remove_sse_session(self, sid):
        self._sse_sessions.pop(sid, None)

    def push_to_sse_session(self, sid, message_dict):
        q = self._sse_sessions.get(sid)
        if q:
            q.put(message_dict)

    def dispatch(self, request_data):
        if isinstance(request_data, list):
            res = []
            for item in request_data:
                if isinstance(item, dict):
                    r = self._dispatch_single(item)
                    if r is not None:
                        res.append(r)
            return res
        elif isinstance(request_data, dict):
            return self._dispatch_single(request_data)
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"}
        }

    def _dispatch_single(self, request_dict):
        method = request_dict.get("method")
        msg_id = request_dict.get("id")
        params = request_dict.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False}
                    },
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION
                    }
                }
            }

        elif method == "notifications/initialized":
            return None

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": TOOLS_DEFINITIONS
                }
            }

        elif method == "resources/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"resources": []}}

        elif method == "prompts/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"prompts": []}}

        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            try:
                res_content = self.execute_tool(tool_name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(res_content, ensure_ascii=False, indent=2, default=str)}
                        ],
                        "isError": False
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": f"Error executing {tool_name}: {str(e)}"}
                        ],
                        "isError": True
                    }
                }

        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not found"
                }
            }

    def execute_tool(self, name, args):
        if name == "mt5_get_status":
            t = mt5.terminal_info()
            v = mt5.version()
            a = mt5.account_info()
            return {
                "service": "MT5 Gateway MCP Server",
                "connected": bool(t.connected if t else False),
                "terminal_version": v,
                "terminal_info": t._asdict() if t else None,
                "account_summary": {
                    "login": a.login if a else None,
                    "server": a.server if a else None,
                    "balance": a.balance if a else None,
                    "equity": a.equity if a else None
                } if a else None
            }

        elif name == "mt5_get_account":
            a = mt5.account_info()
            if not a:
                raise RuntimeError(f"Failed to read account info: {mt5.last_error()}")
            return a._asdict()

        elif name == "mt5_get_tick":
            raw_sym = args.get("symbol", "XAUUSD")
            sym = self.resolve_symbol(raw_sym)
            if self.hub:
                cached = self.hub.get_latest_tick(sym)
                if cached: return cached
            mt5.symbol_select(sym, True)
            t = mt5.symbol_info_tick(sym)
            if not t:
                raise RuntimeError(f"No tick available for {raw_sym} ({sym}): {mt5.last_error()}")
            return {
                "symbol": sym,
                "time": datetime.fromtimestamp(int(t.time)).strftime('%Y-%m-%d %H:%M:%S'),
                "timestamp": int(t.time),
                "bid": float(t.bid),
                "ask": float(t.ask),
                "last": float(t.last),
                "volume": float(t.volume)
            }

        elif name == "mt5_get_rates":
            raw_sym = args.get("symbol", "XAUUSD")
            sym = self.resolve_symbol(raw_sym)
            tf_str = args.get("timeframe", "M1")
            count = int(args.get("count", 500))
            start_pos = int(args.get("start", 0))
            start_time = args.get("start_time")
            end_time = args.get("end_time")
            include_forming = bool(args.get("include_forming", True))

            result = fetch_rates_advanced(
                sym,
                timeframe=tf_str,
                count=count,
                start_pos=start_pos,
                start_time=start_time,
                end_time=end_time,
                include_forming=include_forming
            )
            return result

        elif name == "mt5_list_symbols":
            grp = args.get("group")
            syms = mt5.symbols_get(group=f"*{grp}*") if grp else mt5.symbols_get()
            if not syms: return {"count": 0, "symbols": []}
            names = [s.name for s in syms]
            return {"count": len(names), "symbols": names}

        elif name == "mt5_get_symbol_info":
            raw_sym = args.get("symbol")
            sym = self.resolve_symbol(raw_sym)
            mt5.symbol_select(sym, True)
            info = mt5.symbol_info(sym)
            if not info: raise RuntimeError(f"Symbol {sym} not found")
            return info._asdict()

        elif name == "mt5_get_positions":
            pos = mt5.positions_get()
            if pos is None: return []
            return [p._asdict() for p in pos]

        elif name == "mt5_get_orders":
            orders = mt5.orders_get()
            if orders is None: return []
            return [o._asdict() for o in orders]

        elif name == "mt5_order_send":
            sym = self.resolve_symbol(args.get("symbol"))
            act = args.get("action", "").lower()
            vol = float(args.get("volume", 0.01))
            price = args.get("price")
            mt5.symbol_select(sym, True)
            info = mt5.symbol_info(sym)
            if not info: raise RuntimeError(f"Symbol {sym} unavailable")
            order_type = mt5.ORDER_TYPE_BUY if act == "buy" else mt5.ORDER_TYPE_SELL
            order_price = (info.ask if act == "buy" else info.bid) if price is None else float(price)
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": sym,
                "volume": vol,
                "type": order_type,
                "price": order_price,
                "sl": float(args.get("sl", 0.0)),
                "tp": float(args.get("tp", 0.0)),
                "deviation": 20,
                "magic": 18812,
                "comment": args.get("comment", "MCP Order"),
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res.retcode != mt5.TRADE_RETCODE_DONE:
                raise RuntimeError(f"Order failed with code {res.retcode}: {res.comment}")
            return {"status": "ok", "order": res.order, "deal": res.deal, "price": res.price, "volume": res.volume}

        elif name == "mt5_position_close":
            ticket = int(args.get("ticket"))
            pos = mt5.positions_get(ticket=ticket)
            if not pos: raise RuntimeError(f"Position {ticket} not found")
            p = pos[0]
            close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            info = mt5.symbol_info(p.symbol)
            close_price = info.bid if p.type == mt5.ORDER_TYPE_BUY else info.ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": close_type,
                "position": ticket,
                "price": close_price,
                "deviation": 20,
                "magic": 18812,
                "comment": "MCP Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res.retcode != mt5.TRADE_RETCODE_DONE:
                raise RuntimeError(f"Close failed with code {res.retcode}: {res.comment}")
            return {"status": "ok", "deal": res.deal}

        elif name == "mt5_restart_terminal":
            subprocess.run(["taskkill", "/f", "/im", "terminal64.exe"], capture_output=True)
            time.sleep(1.5)
            subprocess.run(["schtasks", "/run", "/tn", "RunMT5S1"], capture_output=True)
            return {"status": "ok", "message": "MT5 terminal restart triggered in Windows Session 1"}

        elif name == "mt5_restart_gateway":
            subprocess.Popen(["schtasks", "/run", "/tn", "RunMT5Gateway"])
            return {"status": "ok", "message": "Gateway restart triggered"}

        elif name == "mt5_get_logs":
            n = int(args.get("lines", 50))
            log_path = r"C:\Users\Gentleman.Hu\mt5_server.log"
            lines = []
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()[-n:]
                except Exception as e:
                    lines = [f"Error reading log file: {e}"]
            return {"lines_count": len(lines), "logs": "".join(lines)}

        raise ValueError(f"Unknown tool: {name}")
