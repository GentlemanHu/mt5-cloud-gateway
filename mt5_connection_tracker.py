import threading
import time
from datetime import datetime

class ConnectionTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._http_conns = 0
        self._sse_clients = {}      # client_id -> {'addr': ..., 'connected_at': ..., 'symbols': ...}
        self._ws_clients = {}       # client_id -> {'addr': ..., 'connected_at': ..., 'authed': ..., 'symbols': ...}
        self._mcp_sse_clients = {}  # session_id -> {'addr': ..., 'connected_at': ...}
        self._audit_logs = []       # ring buffer of last 150 requests
        self._max_logs = 150

    def record_http_request(self, method, path, ip, auth_user, status, duration_ms):
        with self._lock:
            entry = {
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "method": method,
                "path": path,
                "ip": ip,
                "auth": auth_user or "unauthorized",
                "status": status,
                "duration": f"{duration_ms:.1f}ms"
            }
            self._audit_logs.append(entry)
            if len(self._audit_logs) > self._max_logs:
                self._audit_logs.pop(0)

    def add_sse_client(self, cid, addr, symbols):
        with self._lock:
            self._sse_clients[cid] = {
                "addr": str(addr),
                "connected_at": datetime.now().strftime("%H:%M:%S"),
                "symbols": list(symbols)
            }

    def remove_sse_client(self, cid):
        with self._lock:
            self._sse_clients.pop(cid, None)

    def add_ws_client(self, cid, addr, authed=False, symbols=None):
        with self._lock:
            self._ws_clients[cid] = {
                "addr": str(addr),
                "connected_at": datetime.now().strftime("%H:%M:%S"),
                "authed": authed,
                "symbols": list(symbols or [])
            }

    def update_ws_client(self, cid, authed=None, symbols=None):
        with self._lock:
            if cid in self._ws_clients:
                if authed is not None:
                    self._ws_clients[cid]["authed"] = authed
                if symbols is not None:
                    self._ws_clients[cid]["symbols"] = list(symbols)

    def remove_ws_client(self, cid):
        with self._lock:
            self._ws_clients.pop(cid, None)

    def add_mcp_sse_client(self, sid, addr):
        with self._lock:
            self._mcp_sse_clients[sid] = {
                "addr": str(addr),
                "connected_at": datetime.now().strftime("%H:%M:%S")
            }

    def remove_mcp_sse_client(self, sid):
        with self._lock:
            self._mcp_sse_clients.pop(sid, None)

    def get_stats(self):
        with self._lock:
            return {
                "active_connections": {
                    "total": len(self._sse_clients) + len(self._ws_clients) + len(self._mcp_sse_clients),
                    "market_sse": len(self._sse_clients),
                    "websocket": len(self._ws_clients),
                    "mcp_sse": len(self._mcp_sse_clients)
                },
                "clients_detail": {
                    "sse": list(self._sse_clients.values()),
                    "ws": list(self._ws_clients.values()),
                    "mcp_sse": list(self._mcp_sse_clients.values())
                },
                "recent_audit_logs": list(self._audit_logs)
            }

tracker = ConnectionTracker()
