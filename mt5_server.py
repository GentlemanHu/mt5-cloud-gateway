import http.server
import json
import urllib.parse
from datetime import datetime
import os
import threading
import time
import socket
import struct
import hashlib
import base64
import subprocess
import concurrent.futures
import traceback
import queue

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import MetaTrader5 as mt5
from mt5_mcp_core import McpDispatcher, TOOLS_DEFINITIONS, TIMEFRAME_MAP
from mt5_kline_engine import fetch_rates_advanced, parse_timeframe
from mt5_token_manager import token_manager
from mt5_connection_tracker import tracker
from mt5_docs import LOGIN_PAGE_HTML, get_docs_html, get_llms_txt, get_openapi_json

HTTP_PORT = int(os.environ.get('MT5_HTTP_PORT', 18812))
WS_PORT = int(os.environ.get('MT5_WS_PORT', 18813))
HOST = os.environ.get('MT5_HOST', '0.0.0.0')
PANEL_PASSWORD = os.environ.get('MT5_PANEL_PASSWORD', 'admin123456')
_mt5_lock = threading.Lock()
_connected, _last_error = False, None
_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=16)
_symbol_cache, _symbol_lower_map, _symbol_cache_time = set(), {}, 0

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def resolve_symbol(symbol):
    global _symbol_cache, _symbol_lower_map
    if not symbol: return None
    s = symbol.strip()
    if s in _symbol_cache: return s
    s_lower = s.lower()
    if s_lower in _symbol_lower_map: return _symbol_lower_map[s_lower]

    # Try common broker symbol variations and suffixes
    for suffix in ['m', 'c', '.pro', '.raw', '.r', '.a', '_i']:
        if (s_lower + suffix) in _symbol_lower_map:
            return _symbol_lower_map[s_lower + suffix]

    # Try stripping suffix if input had one
    for suffix in ['m', 'c', '.pro', '.raw', '.r', '.a', '_i']:
        if s_lower.endswith(suffix):
            trimmed = s_lower[:-len(suffix)]
            if trimmed in _symbol_lower_map:
                return _symbol_lower_map[trimmed]
    return s

def init_mt5(login=None, password=None, server=None):
    global _connected, _last_error, _symbol_cache, _symbol_lower_map, _symbol_cache_time
    with _mt5_lock:
        try:
            log("Attempting mt5.initialize()...")
            login = login or os.environ.get('MT5_LOGIN')
            password = password or os.environ.get('MT5_PASSWORD')
            server = server or os.environ.get('MT5_SERVER')
            custom_path = os.environ.get('MT5_PATH')

            kwargs = {}
            if login: kwargs['login'] = int(login)
            if password: kwargs['password'] = str(password)
            if server: kwargs['server'] = str(server)
            if custom_path: kwargs['path'] = str(custom_path)

            ok = mt5.initialize(timeout=5000, **kwargs)
            if not ok and 'path' not in kwargs:
                common_paths = [
                    r"C:\Program Files\MetaTrader 5\terminal64.exe",
                    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
                ]
                for p in common_paths:
                    if os.path.exists(p):
                        ok = mt5.initialize(path=p, timeout=5000, **kwargs)
                        if ok: break
            _connected = bool(ok)
            if not ok:
                _last_error = mt5.last_error()
                log(f"MT5 Init Failed: {_last_error}")
            else:
                log(f"MT5 Init Success! Terminal: {mt5.terminal_info()}")
                try:
                    all_syms = mt5.symbols_get()
                    if all_syms:
                        _symbol_cache = {s.name for s in all_syms}
                        _symbol_lower_map = {s.name.lower(): s.name for s in all_syms}
                        _symbol_cache_time = time.time()
                        for sym in ['EURUSD', 'EURUSDm', 'GBPUSD', 'GBPUSDm', 'USDJPY', 'USDJPYm', 'XAUUSD', 'XAUUSDm', 'BTCUSD', 'BTCUSDm', 'ETHUSD', 'ETHUSDm']:
                            if sym in _symbol_cache: mt5.symbol_select(sym, True)
                except Exception as e:
                    log(f"Failed to cache symbols: {e}")
            return _connected
        except Exception as e:
            _connected, _last_error = False, str(e)
            log(f"Exception during MT5 init: {e}")
            return False

def run_with_timeout(func, args=(), kwargs=None, timeout=2.5):
    if kwargs is None: kwargs = {}
    future = _thread_pool.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=timeout), None
    except concurrent.futures.TimeoutError:
        return None, "Operation timed out (MT5 pipeline busy)"
    except Exception as e:
        return None, str(e)

class QuotationHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest_ticks = {}
        self._subscribers = set()

    def update_tick(self, symbol, tick_dict):
        with self._lock:
            old = self._latest_ticks.get(symbol)
            if not old or old.get('time_msc') != tick_dict.get('time_msc'):
                self._latest_ticks[symbol] = tick_dict
                for sub in list(self._subscribers):
                    try: sub(symbol, tick_dict)
                    except Exception: pass

    def get_latest_tick(self, symbol):
        resolved = resolve_symbol(symbol)
        with self._lock:
            if resolved in self._latest_ticks:
                return self._latest_ticks[resolved]
        if _connected:
            try:
                mt5.symbol_select(resolved, True)
                t = mt5.symbol_info_tick(resolved)
                if t:
                    d = {
                        'symbol': resolved,
                        'time': datetime.fromtimestamp(int(t.time)).strftime('%Y-%m-%d %H:%M:%S'),
                        'timestamp': int(t.time), 'time_msc': int(t.time_msc),
                        'bid': float(t.bid), 'ask': float(t.ask), 'last': float(t.last),
                        'volume': float(t.volume), 'flags': int(t.flags)
                    }
                    self.update_tick(resolved, d)
                    return d
            except Exception: pass
        return None

hub = QuotationHub()
mcp_dispatcher = McpDispatcher(resolve_symbol, hub)

def background_tick_poller():
    base_symbols = ['EURUSD', 'XAUUSD', 'GBPUSD', 'USDJPY', 'BTCUSD', 'ETHUSD']
    while True:
        try:
            if _connected:
                for base in base_symbols:
                    sym = resolve_symbol(base)
                    if sym:
                        mt5.symbol_select(sym, True)
                        t = mt5.symbol_info_tick(sym)
                        if t and t.bid > 0:
                            d = {
                                'symbol': sym,
                                'time': datetime.fromtimestamp(int(t.time)).strftime('%Y-%m-%d %H:%M:%S'),
                                'timestamp': int(t.time), 'time_msc': int(t.time_msc),
                                'bid': float(t.bid), 'ask': float(t.ask), 'last': float(t.last),
                                'volume': float(t.volume), 'flags': int(t.flags)
                            }
                            hub.update_tick(sym, d)
            time.sleep(0.08)
        except Exception:
            time.sleep(1.0)

class MT5Handler(http.server.BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, HEAD')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-API-Key, MCP-Protocol-Version')
            if getattr(self, 'path', '').startswith('/mcp'):
                self.send_header('MCP-Protocol-Version', '2026-07-28')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            log(f"Error in send_json: {e}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, HEAD')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-API-Key')
        self.end_headers()

    def do_HEAD(self): self.do_GET()

    def authenticate_request(self):
        """Returns (is_authed, auth_type, identity_name)."""
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        # 1. Check Panel Session Cookie
        cookie_hdr = self.headers.get('Cookie', '')
        if cookie_hdr:
            for item in cookie_hdr.split(';'):
                if '=' in item:
                    k, v = item.strip().split('=', 1)
                    if k == 'mt5_panel_session' and v == PANEL_PASSWORD:
                        return True, 'panel_admin', 'AdminSession'

        # 2. Check API / MCP Token in Query (?token=...)
        token_q = qs.get('token', [None])[0]
        if token_q:
            if token_q == PANEL_PASSWORD:
                return True, 'panel_admin', 'AdminToken'
            ok, name = token_manager.validate_token(token_q)
            if ok: return True, 'api_token', name

        # 3. Check Authorization Header (Bearer <token>)
        auth_hdr = self.headers.get('Authorization', '')
        if auth_hdr.startswith('Bearer '):
            token_bearer = auth_hdr.split('Bearer ', 1)[1].strip()
            if token_bearer == PANEL_PASSWORD:
                return True, 'panel_admin', 'AdminBearer'
            ok, name = token_manager.validate_token(token_bearer)
            if ok: return True, 'api_token', name

        # 4. Check X-API-Key Header
        api_key = self.headers.get('X-API-Key', '').strip()
        if api_key:
            if api_key == PANEL_PASSWORD:
                return True, 'panel_admin', 'AdminKey'
            ok, name = token_manager.validate_token(api_key)
            if ok: return True, 'api_token', name

        return False, None, None

    def do_GET(self):
        global _connected
        start_t = time.time()
        client_ip = self.headers.get('CF-Connecting-IP') or self.client_address[0]
        try:
            parsed = urllib.parse.urlparse(self.path)
            path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)

            if path == '/login':
                b = LOGIN_PAGE_HTML.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return

            # Public AI & Developer Documentation endpoints
            if path in ['/docs', '/api/docs', '/api-docs']:
                b = get_docs_html()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return

            if path in ['/llms.txt', '/llms-full.txt']:
                b = get_llms_txt()
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return

            if path in ['/openapi.json', '/docs.json']:
                b = get_openapi_json()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return

            # Public Portable Stdio MCP Client Download (Zero Machine Path Leakage)
            if path in ['/mcp/client.py', '/mcp/stdio.py']:
                client_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mt5_mcp_stdio.py')
                client_bytes = b""
                if os.path.exists(client_path):
                    with open(client_path, 'rb') as f:
                        client_bytes = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/x-python; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Disposition', 'attachment; filename="mt5_mcp_client.py"')
                self.send_header('Content-Length', str(len(client_bytes)))
                self.end_headers()
                self.wfile.write(client_bytes)
                return

            is_authed, auth_type, auth_name = self.authenticate_request()
            dur_ms = (time.time() - start_t) * 1000

            # Unauthenticated web request -> Show Login Page
            if not is_authed:
                tracker.record_http_request("GET", path, client_ip, None, 401, dur_ms)
                if path in ['/', '/dashboard'] or 'text/html' in self.headers.get('Accept', ''):
                    b = LOGIN_PAGE_HTML.encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(b)))
                    self.end_headers()
                    self.wfile.write(b)
                    return
                return self.send_json({'error': 'Unauthorized', 'message': 'Authentication required'}, status=401)

            tracker.record_http_request("GET", path, client_ip, auth_name, 200, dur_ms)

            # Web Management Dashboard HTML (Requires Panel Admin)
            if path in ['/', '/dashboard']:
                dash_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web_dashboard.html')
                if os.path.exists(dash_file):
                    with open(dash_file, 'rb') as f: html_bytes = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Content-Length', str(len(html_bytes)))
                    self.end_headers()
                    self.wfile.write(html_bytes)
                    return

            # MCP Status Ping on GET (/mcp)
            if path == '/mcp':
                return self.send_json({
                    "service": "MT5 MCP Streamable HTTP Gateway",
                    "protocol": "MCP",
                    "protocolVersion": "2026-07-28",
                    "supportedVersions": ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"],
                    "status": "ready",
                    "tools_count": len(TOOLS_DEFINITIONS)
                })
            if path == '/api/connections':
                return self.send_json({'status': 'ok', 'data': tracker.get_stats()})

            # Token Management API (/api/tokens)
            if path == '/api/tokens':
                return self.send_json({'status': 'ok', 'tokens': token_manager.list_tokens(mask=False)})

            # SSE MCP Endpoint (/mcp/sse)
            if path == '/mcp/sse':
                sid, q = mcp_dispatcher.create_sse_session()
                tracker.add_mcp_sse_client(sid, client_ip)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'keep-alive')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('MCP-Protocol-Version', '2026-07-28')
                self.end_headers()
                active_token = token_manager.list_tokens()[0]['token'] if token_manager.list_tokens() else ''
                ep_msg = f"event: endpoint\ndata: /mcp/messages?session_id={sid}&token={active_token}\n\n"
                self.wfile.write(ep_msg.encode('utf-8'))
                self.wfile.flush()
                try:
                    while True:
                        try:
                            msg = q.get(timeout=15.0)
                            out = f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                            self.wfile.write(out.encode('utf-8'))
                            self.wfile.flush()
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                except Exception: pass
                finally:
                    tracker.remove_mcp_sse_client(sid)
                    mcp_dispatcher.remove_sse_session(sid)
                return

            if path == '/logs':
                log_file = os.environ.get('MT5_LOG_FILE', os.path.join(os.path.dirname(os.path.abspath(__file__)), "mt5_server.log"))
                lines = []
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()[-80:]
                    except Exception: pass
                content = "".join(lines).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            if path in ['/health', '/status']:
                t_info, v_info, acc_info = None, None, None
                if _connected:
                    try:
                        t = mt5.terminal_info(); t_info = t._asdict() if t else None
                        v_info = mt5.version(); a = mt5.account_info()
                        acc_info = {
                            'login': a.login, 'server': a.server, 'balance': a.balance,
                            'equity': a.equity, 'connected': getattr(a, 'connected', t.connected)
                        } if a else None
                    except Exception: pass
                host_part = self.headers.get('Host', f'localhost:{HTTP_PORT}').split(':')[0]
                ws_url = f'ws://{host_part}:{WS_PORT}'
                return self.send_json({
                    'status': 'ok', 'service': 'MT5 HTTP & Stream Gateway', 'auth_enabled': True,
                    'mt5_connected': _connected, 'last_error': _last_error,
                    'terminal_version': v_info, 'terminal_info': t_info, 'account': acc_info,
                    'active_connections': tracker.get_stats()['active_connections'],
                    'stream_endpoints': {
                        'tick_stream': f'/stream?symbols=XAUUSD,EURUSD',
                        'kline_stream': f'/rates/stream?symbol=XAUUSD&timeframe=M1',
                        'websocket': ws_url
                    }
                })

            if path in ['/stream', '/events', '/sse']:
                self.handle_sse(qs, client_ip)
                return

            if path in ['/rates/stream', '/kline/stream']:
                self.handle_kline_sse(qs, client_ip)
                return

            if not _connected:
                init_mt5()
                if not _connected:
                    return self.send_json({'error': 'MT5 terminal not connected'}, status=503)

            if path == '/account':
                res, err = run_with_timeout(mt5.account_info, timeout=2.0)
                if err or res is None: return self.send_json({'error': err or 'Account info unavailable'}, status=500)
                return self.send_json({'status': 'ok', 'data': res._asdict()})

            elif path == '/symbols':
                group = qs.get('group', [None])[0]
                def get_syms(): return mt5.symbols_get(group=f"*{group}*") if group else mt5.symbols_get()
                syms, err = run_with_timeout(get_syms, timeout=3.0)
                if err or syms is None: return self.send_json({'error': err or 'Failed to get symbols'}, status=500)
                return self.send_json({'status': 'ok', 'count': len(syms), 'data': [s.name for s in syms]})

            elif path == '/symbol_info':
                raw_sym = qs.get('symbol', [None])[0]
                if not raw_sym: return self.send_json({'error': 'symbol required'}, status=400)
                sym = resolve_symbol(raw_sym)
                def get_info():
                    mt5.symbol_select(sym, True)
                    return mt5.symbol_info(sym)
                info, err = run_with_timeout(get_info, timeout=2.0)
                if err or info is None: return self.send_json({'error': f'Symbol {raw_sym} not found'}, status=404)
                return self.send_json({'status': 'ok', 'symbol': sym, 'data': info._asdict()})

            elif path in ['/tick', '/latest_tick']:
                raw_sym = qs.get('symbol', ['EURUSD'])[0]
                sym = resolve_symbol(raw_sym)
                cached = hub.get_latest_tick(sym)
                if cached: return self.send_json({'status': 'ok', 'symbol': sym, 'data': cached})
                def get_tick():
                    mt5.symbol_select(sym, True)
                    return mt5.symbol_info_tick(sym)
                t, err = run_with_timeout(get_tick, timeout=2.0)
                if err or t is None: return self.send_json({'error': f'No tick for {raw_sym}'}, status=404)
                d = {
                    'symbol': sym, 'time': datetime.fromtimestamp(int(t.time)).strftime('%Y-%m-%d %H:%M:%S'),
                    'timestamp': int(t.time), 'bid': float(t.bid), 'ask': float(t.ask),
                    'last': float(t.last), 'volume': float(t.volume), 'flags': int(t.flags)
                }
                return self.send_json({'status': 'ok', 'symbol': sym, 'data': d})

            elif path in ['/rates', '/kline']:
                raw_sym = qs.get('symbol', ['XAUUSD'])[0]
                sym = resolve_symbol(raw_sym)
                tf_str = qs.get('timeframe', ['M1'])[0]
                count = int(qs.get('count', [qs.get('limit', [500])[0]])[0])
                start_pos = int(qs.get('start', [qs.get('offset', [0])[0]])[0])
                start_time = qs.get('start_time', [qs.get('from', [qs.get('from_time', [None])[0]])[0]])[0]
                end_time = qs.get('end_time', [qs.get('to', [qs.get('to_time', [None])[0]])[0]])[0]
                inc_f_str = qs.get('include_forming', ['true'])[0].lower()
                include_forming = inc_f_str in ['true', '1', 'yes']

                def get_rates():
                    return fetch_rates_advanced(
                        sym,
                        timeframe=tf_str,
                        count=count,
                        start_pos=start_pos,
                        start_time=start_time,
                        end_time=end_time,
                        include_forming=include_forming
                    )
                res, err = run_with_timeout(get_rates, timeout=5.0)
                if err or res is None:
                    return self.send_json({'error': f'Failed to get rates: {err}'}, status=500)
                return self.send_json(res)

            elif path == '/positions':
                pos, err = run_with_timeout(mt5.positions_get, timeout=2.0)
                if pos is None: return self.send_json({'status': 'ok', 'count': 0, 'data': []})
                return self.send_json({'status': 'ok', 'count': len(pos), 'data': [p._asdict() for p in pos]})

            elif path == '/orders':
                orders, err = run_with_timeout(mt5.orders_get, timeout=2.0)
                if orders is None: return self.send_json({'status': 'ok', 'count': 0, 'data': []})
                return self.send_json({'status': 'ok', 'count': len(orders), 'data': [o._asdict() for o in orders]})

            return self.send_json({'error': f'Endpoint {path} not found'}, status=404)

        except Exception as e:
            traceback.print_exc()
            return self.send_json({'error': 'Internal server error', 'exception': str(e)}, status=500)

    def handle_sse(self, qs, client_ip):
        symbols_param = qs.get('symbols', ['EURUSD,XAUUSD,USDJPY'])[0]
        symbols = [resolve_symbol(s.strip()) for s in symbols_param.split(',') if s.strip()]
        interval = float(qs.get('interval', [0.08])[0])
        cid = f"sse_{int(time.time()*1000)}_{self.client_address[1]}"
        tracker.add_sse_client(cid, client_ip, symbols)

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        init_data = json.dumps({'status': 'connected', 'subscribed_symbols': symbols})
        self.wfile.write(f"event: ready\ndata: {init_data}\n\n".encode('utf-8'))
        self.wfile.flush()

        last_pushed = {}
        try:
            while True:
                for sym in symbols:
                    t = hub.get_latest_tick(sym)
                    if t:
                        last = last_pushed.get(sym)
                        if not last or last.get('timestamp') != t.get('timestamp') or last.get('bid') != t.get('bid') or last.get('ask') != t.get('ask'):
                            last_pushed[sym] = t
                            msg = f"event: tick\ndata: {json.dumps(t, ensure_ascii=False)}\n\n"
                            self.wfile.write(msg.encode('utf-8'))
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                time.sleep(max(0.05, interval))
        except (BrokenPipeError, ConnectionResetError): pass
        finally:
            tracker.remove_sse_client(cid)

    def handle_kline_sse(self, qs, client_ip):
        raw_sym = qs.get('symbol', ['XAUUSD'])[0]
        sym = resolve_symbol(raw_sym)
        tf_str = qs.get('timeframe', ['M1'])[0]
        interval = float(qs.get('interval', [0.1])[0])

        try:
            canonical_tf, tf_const, tf_seconds = parse_timeframe(tf_str)
        except Exception as e:
            self.send_json({'error': str(e)}, status=400)
            return

        cid = f"kline_sse_{int(time.time()*1000)}_{self.client_address[1]}"
        tracker.add_sse_client(cid, client_ip, [f"{sym}_{canonical_tf}"])

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        initial_data = fetch_rates_advanced(sym, canonical_tf, count=2, include_forming=True)
        init_payload = {
            'status': 'connected',
            'symbol': sym,
            'timeframe': canonical_tf,
            'timeframe_seconds': tf_seconds,
            'initial_rates': initial_data.get('data', [])
        }
        self.wfile.write(f"event: ready\ndata: {json.dumps(init_payload, ensure_ascii=False)}\n\n".encode('utf-8'))
        self.wfile.flush()

        last_bar_timestamp = None
        last_bar_close = None
        last_bar_vol = None

        if initial_data.get('data'):
            forming = initial_data['data'][-1]
            last_bar_timestamp = forming['timestamp']
            last_bar_close = forming['close']
            last_bar_vol = forming['tick_volume']

        last_ping_time = time.time()
        try:
            while True:
                time.sleep(max(0.08, interval))
                now = time.time()
                if now - last_ping_time > 15:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    last_ping_time = now

                live_res = fetch_rates_advanced(sym, canonical_tf, count=2, include_forming=True)
                if not live_res or not live_res.get('data'):
                    continue

                bars = live_res['data']
                curr_bar = bars[-1]

                if last_bar_timestamp is not None and curr_bar['timestamp'] > last_bar_timestamp:
                    closed_bar = bars[0]
                    self.wfile.write(f"event: kline_closed\ndata: {json.dumps(closed_bar, ensure_ascii=False)}\n\n".encode('utf-8'))
                    self.wfile.write(f"event: kline_open\ndata: {json.dumps(curr_bar, ensure_ascii=False)}\n\n".encode('utf-8'))
                    self.wfile.flush()

                    last_bar_timestamp = curr_bar['timestamp']
                    last_bar_close = curr_bar['close']
                    last_bar_vol = curr_bar['tick_volume']

                elif (curr_bar['close'] != last_bar_close or curr_bar['tick_volume'] != last_bar_vol):
                    self.wfile.write(f"event: kline_update\ndata: {json.dumps(curr_bar, ensure_ascii=False)}\n\n".encode('utf-8'))
                    self.wfile.flush()

                    last_bar_close = curr_bar['close']
                    last_bar_vol = curr_bar['tick_volume']
                    last_bar_timestamp = curr_bar['timestamp']

        except (BrokenPipeError, ConnectionResetError): pass
        except Exception: pass
        finally:
            tracker.remove_sse_client(cid)

    def do_POST(self):
        global _connected, _symbol_cache, _symbol_lower_map
        start_t = time.time()
        client_ip = self.headers.get('CF-Connecting-IP') or self.client_address[0]
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            length = int(self.headers.get('Content-Length', 0))
            req_data = {}
            if length > 0:
                raw = self.rfile.read(length).decode('utf-8')
                try: req_data = json.loads(raw)
                except Exception: pass

            # Form Login Handler (Authenticates with PANEL_PASSWORD)
            if path == '/auth/login':
                pwd = req_data.get('password', '').strip()
                if pwd == PANEL_PASSWORD:
                    tracker.record_http_request("POST", path, client_ip, "AdminLogin", 200, (time.time()-start_t)*1000)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Set-Cookie', f'mt5_panel_session={PANEL_PASSWORD}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000')
                    self.end_headers()
                    self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))
                    return
                tracker.record_http_request("POST", path, client_ip, "FailedLogin", 401, (time.time()-start_t)*1000)
                return self.send_json({'status': 'failed', 'message': 'Invalid password'}, status=401)

            # GLOBAL AUTH CHECK FOR POST
            is_authed, auth_type, auth_name = self.authenticate_request()
            dur_ms = (time.time() - start_t) * 1000
            if not is_authed:
                tracker.record_http_request("POST", path, client_ip, None, 401, dur_ms)
                return self.send_json({'error': 'Unauthorized', 'message': 'Authentication required'}, status=401)

            tracker.record_http_request("POST", path, client_ip, auth_name, 200, dur_ms)

            # ----------------- MCP Server Protocols -----------------
            if path == '/mcp':
                resp = mcp_dispatcher.dispatch(req_data)
                if resp is None:
                    self.send_response(204)
                    self.end_headers()
                    return
                return self.send_json(resp)

            elif path == '/mcp/messages':
                sid = urllib.parse.parse_qs(parsed.query).get('session_id', [None])[0]
                resp = mcp_dispatcher.dispatch(req_data)
                if sid and resp is not None:
                    mcp_dispatcher.push_to_sse_session(sid, resp)
                self.send_response(202)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b"Accepted")
                return

            # Token Lifecycle APIs (Create / Regenerate / Revoke / Delete)
            elif path == '/api/tokens/create':
                name = req_data.get('name', 'API Token')
                item = token_manager.create_token(name)
                return self.send_json({'status': 'ok', 'token': item})

            elif path == '/api/tokens/regenerate':
                tid = req_data.get('id')
                item = token_manager.regenerate_token(tid)
                if item: return self.send_json({'status': 'ok', 'token': item})
                return self.send_json({'error': 'Token not found'}, status=404)

            elif path == '/api/tokens/revoke':
                tid = req_data.get('id')
                if token_manager.revoke_token(tid):
                    return self.send_json({'status': 'ok', 'message': 'Token revoked'})
                return self.send_json({'error': 'Token not found'}, status=404)

            elif path == '/api/tokens/delete':
                tid = req_data.get('id')
                if token_manager.delete_token(tid):
                    return self.send_json({'status': 'ok', 'message': 'Token deleted'})
                return self.send_json({'error': 'Token not found'}, status=404)

            # Service Controls
            elif path == '/restart_mt5':
                def do_restart():
                    subprocess.run(["taskkill", "/f", "/im", "terminal64.exe"], capture_output=True)
                    time.sleep(1.5)
                    subprocess.run(["schtasks", "/run", "/tn", "RunMT5S1"], capture_output=True)
                    time.sleep(3.0)
                    init_mt5()
                threading.Thread(target=do_restart, daemon=True).start()
                return self.send_json({'status': 'ok', 'message': 'MT5 terminal restart triggered in Windows Session 1'})

            elif path == '/restart_gateway':
                def do_restart_gw():
                    time.sleep(1.0)
                    subprocess.run(["schtasks", "/run", "/tn", "RunMT5Gateway"], capture_output=True)
                threading.Thread(target=do_restart_gw, daemon=True).start()
                return self.send_json({'status': 'ok', 'message': 'Gateway restart initiated'})

            elif path == '/resync_symbols':
                all_syms = mt5.symbols_get()
                if all_syms:
                    _symbol_cache = {s.name for s in all_syms}
                    _symbol_lower_map = {s.name.lower(): s.name for s in all_syms}
                    for sym in ['EURUSDm', 'GBPUSDm', 'USDJPYm', 'XAUUSDm', 'BTCUSDm', 'ETHUSDm']:
                        if sym in _symbol_cache: mt5.symbol_select(sym, True)
                return self.send_json({'status': 'ok', 'count': len(_symbol_cache), 'message': 'Symbols cache reloaded'})

            if not _connected:
                init_mt5()
                if not _connected: return self.send_json({'error': 'MT5 terminal not connected'}, status=503)

            if path == '/order':
                raw_sym = req_data.get('symbol')
                action = req_data.get('action', '').lower()
                volume = float(req_data.get('volume', 0.01))
                price = req_data.get('price')
                sl, tp = float(req_data.get('sl', 0.0)), float(req_data.get('tp', 0.0))
                comment = req_data.get('comment', 'API Order')

                if not raw_sym or action not in ['buy', 'sell']:
                    return self.send_json({'error': 'symbol and action required'}, status=400)

                symbol = resolve_symbol(raw_sym)
                mt5.symbol_select(symbol, True)
                info = mt5.symbol_info(symbol)
                if not info: return self.send_json({'error': f'Symbol {symbol} unavailable'}, status=404)

                order_type = mt5.ORDER_TYPE_BUY if action == 'buy' else mt5.ORDER_TYPE_SELL
                order_price = (info.ask if action == 'buy' else info.bid) if price is None else float(price)

                request = {
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume,
                    "type": order_type, "price": order_price, "sl": sl, "tp": tp,
                    "deviation": 20, "magic": 18812, "comment": comment,
                    "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
                }
                res = mt5.order_send(request)
                if res.retcode != mt5.TRADE_RETCODE_DONE:
                    return self.send_json({'status': 'failed', 'retcode': res.retcode, 'comment': res.comment}, status=400)
                return self.send_json({'status': 'ok', 'order': res.order, 'deal': res.deal, 'volume': res.volume, 'price': res.price})

            elif path == '/close':
                ticket = int(req_data.get('ticket', 0))
                pos = mt5.positions_get(ticket=ticket)
                if not pos: return self.send_json({'error': f'Position {ticket} not found'}, status=404)
                p = pos[0]
                close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                info = mt5.symbol_info(p.symbol)
                request = {
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
                    "type": close_type, "position": ticket,
                    "price": info.bid if p.type == mt5.ORDER_TYPE_BUY else info.ask,
                    "deviation": 20, "magic": 18812, "comment": "API Close",
                    "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
                }
                res = mt5.order_send(request)
                if res.retcode != mt5.TRADE_RETCODE_DONE:
                    return self.send_json({'status': 'failed', 'retcode': res.retcode, 'comment': res.comment}, status=400)
                return self.send_json({'status': 'ok', 'deal': res.deal})

            return self.send_json({'error': f'Endpoint {path} not found'}, status=404)

        except Exception as e:
            traceback.print_exc()
            return self.send_json({'error': 'Internal server error', 'exception': str(e)}, status=500)

def start_websocket_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', WS_PORT))
    server_socket.listen(32)
    log(f"WebSocket Server listening on ws://0.0.0.0:{WS_PORT}...")

    def encode_ws_frame(payload_bytes, opcode=1):
        length = len(payload_bytes)
        if length <= 125: header = struct.pack('!BB', 0x80 | opcode, length)
        elif length <= 65535: header = struct.pack('!BBH', 0x80 | opcode, 126, length)
        else: header = struct.pack('!BBQ', 0x80 | opcode, 127, length)
        return header + payload_bytes

    def handle_ws_client(client_sock, client_addr):
        cid = f"ws_{int(time.time()*1000)}_{client_addr[1]}"
        try:
            data = client_sock.recv(4096).decode('utf-8', errors='ignore')
            sec_key, authed = None, False
            first_line = data.split('\r\n')[0] if data else ''
            if '?' in first_line:
                qs_str = first_line.split('?')[1].split(' ')[0]
                q_token = urllib.parse.parse_qs(qs_str).get('token', [None])[0]
                if q_token:
                    authed = (q_token == PANEL_PASSWORD) or token_manager.validate_token(q_token)[0]

            for line in data.split('\r\n'):
                if line.lower().startswith('sec-websocket-key:'):
                    sec_key = line.split(':', 1)[1].strip()
                elif line.lower().startswith('authorization:'):
                    val = line.split(':', 1)[1].strip()
                    if val.startswith('Bearer '):
                        tok = val.split('Bearer ', 1)[1].strip()
                        authed = (tok == PANEL_PASSWORD) or token_manager.validate_token(tok)[0]
                elif line.lower().startswith('x-api-key:'):
                    tok = line.split(':', 1)[1].strip()
                    authed = (tok == PANEL_PASSWORD) or token_manager.validate_token(tok)[0]

            if not sec_key:
                client_sock.close()
                return

            accept_key = base64.b64encode(hashlib.sha1((sec_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode('utf-8')).digest()).decode('utf-8')
            response = ("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n")
            client_sock.sendall(response.encode('utf-8'))
            log(f"WebSocket client connected: {client_addr}, authed={authed}")

            subscribed_symbols = {'EURUSDm', 'XAUUSDm'}
            tracker.add_ws_client(cid, client_addr[0], authed=authed, symbols=subscribed_symbols)
            last_sent = {}
            welcome = json.dumps({'event': 'welcome', 'status': 'connected', 'authenticated': authed, 'subscribed': list(subscribed_symbols)})
            client_sock.sendall(encode_ws_frame(welcome.encode('utf-8')))
            client_sock.settimeout(0.1)

            while True:
                try:
                    raw = client_sock.recv(4096)
                    if raw and len(raw) >= 2:
                        masked = (raw[1] & 0x80) != 0
                        payload_len = raw[1] & 0x7F
                        offset = 2
                        if payload_len == 126: payload_len, offset = struct.unpack('!H', raw[2:4])[0], 4
                        elif payload_len == 127: payload_len, offset = struct.unpack('!Q', raw[2:10])[0], 10
                        if masked:
                            mask = raw[offset:offset+4]
                            masked_data = raw[offset+4:offset+4+payload_len]
                            unmasked = bytes(b ^ mask[i % 4] for i, b in enumerate(masked_data))
                            try:
                                cmd = json.loads(unmasked.decode('utf-8', errors='ignore'))
                                if cmd.get('action') == 'auth':
                                    tok = cmd.get('token')
                                    if tok == PANEL_PASSWORD: authed = True
                                    else:
                                        ok, _ = token_manager.validate_token(tok)
                                        authed = ok
                                    tracker.update_ws_client(cid, authed=authed)
                                    status_str = 'ok' if authed else 'failed'
                                    client_sock.sendall(encode_ws_frame(json.dumps({'event': 'auth', 'status': status_str}).encode('utf-8')))
                                elif cmd.get('action') == 'subscribe':
                                    for s in cmd.get('symbols', []): subscribed_symbols.add(resolve_symbol(s))
                                    tracker.update_ws_client(cid, symbols=subscribed_symbols)
                                    resp = json.dumps({'event': 'subscribed', 'symbols': list(subscribed_symbols)})
                                    client_sock.sendall(encode_ws_frame(resp.encode('utf-8')))
                                elif cmd.get('action') == 'unsubscribe':
                                    for s in cmd.get('symbols', []): subscribed_symbols.discard(resolve_symbol(s))
                                    tracker.update_ws_client(cid, symbols=subscribed_symbols)
                                    resp = json.dumps({'event': 'unsubscribed', 'symbols': list(subscribed_symbols)})
                                    client_sock.sendall(encode_ws_frame(resp.encode('utf-8')))
                            except Exception: pass
                except socket.timeout: pass

                if authed:
                    for sym in list(subscribed_symbols):
                        t = hub.get_latest_tick(sym)
                        if t:
                            last = last_sent.get(sym)
                            if not last or last.get('timestamp') != t.get('timestamp') or last.get('bid') != t.get('bid') or last.get('ask') != t.get('ask'):
                                last_sent[sym] = t
                                frame = encode_ws_frame(json.dumps({'event': 'tick', 'data': t}, ensure_ascii=False).encode('utf-8'))
                                client_sock.sendall(frame)
                time.sleep(0.08)

        except (BrokenPipeError, ConnectionResetError, socket.error): pass
        finally:
            tracker.remove_ws_client(cid)
            try: client_sock.close()
            except Exception: pass

    while True:
        try:
            client, addr = server_socket.accept()
            threading.Thread(target=handle_ws_client, args=(client, addr), daemon=True).start()
        except Exception: time.sleep(1)

def start_optional_cloudflared():
    tunnel_token = os.environ.get('CLOUDFLARE_TUNNEL_TOKEN', '').strip()
    if not tunnel_token:
        log(f"[Tunnel] No CLOUDFLARE_TUNNEL_TOKEN provided. Running in pure local/LAN mode on http://{HOST}:{HTTP_PORT}")
        return

    cf_bin = "cloudflared.exe" if os.name == 'nt' else "cloudflared"
    has_cf = False
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.exists(os.path.join(path_dir, cf_bin)):
            has_cf = True
            break
    if not has_cf and os.path.exists(cf_bin):
        has_cf = True

    if not has_cf:
        log(f"[Tunnel] '{cf_bin}' not found in PATH or project folder. Please install cloudflared or place it in the folder.")
        return

    log(f"[Tunnel] CLOUDFLARE_TUNNEL_TOKEN detected. Starting Cloudflare Tunnel daemon ({cf_bin})...")
    cmd = [cf_bin, "tunnel", "run", "--token", tunnel_token]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"[Tunnel] Cloudflare Tunnel daemon running (PID: {proc.pid}).")
    except Exception as e:
        log(f"[Tunnel] Failed to start Cloudflare Tunnel: {e}")

def run():
    log(f"Starting MT5 HTTP & Streaming Gateway on {HOST}:{HTTP_PORT}...")
    httpd = http.server.ThreadingHTTPServer((HOST, HTTP_PORT), MT5Handler)
    log(f"HTTP Server successfully bound to {HOST}:{HTTP_PORT}.")
    for target in [init_mt5, background_tick_poller, start_websocket_server, start_optional_cloudflared]:
        threading.Thread(target=target, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        try: mt5.shutdown()
        except Exception: pass
        httpd.server_close()

if __name__ == '__main__':
    run()
