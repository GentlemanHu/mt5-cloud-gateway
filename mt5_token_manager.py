import json
import os
import secrets
import threading
from datetime import datetime

TOKENS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens.json")
_lock = threading.Lock()

class TokenManager:
    def __init__(self, file_path=TOKENS_FILE):
        self.file_path = file_path
        self.tokens = []
        self._load()

    def _load(self):
        with _lock:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        self.tokens = json.load(f)
                    return
                except Exception:
                    self.tokens = []

            # Initialize with default primary token
            default_token = "mt5_live_" + secrets.token_hex(16)
            self.tokens = [
                {
                    "id": "tok_default",
                    "name": "Default Primary API & MCP Token",
                    "token": default_token,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "last_used_at": None,
                    "use_count": 0,
                    "status": "active"
                }
            ]
            self._save_unlocked()

    def _save_unlocked(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.tokens, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TokenManager] Failed to save tokens: {e}", flush=True)

    def list_tokens(self, mask=False):
        with _lock:
            res = []
            for t in self.tokens:
                item = dict(t)
                if mask:
                    val = item.get("token", "")
                    if len(val) > 10:
                        item["token_masked"] = val[:6] + "..." + val[-4:]
                    else:
                        item["token_masked"] = "******"
                res.append(item)
            return res

    def validate_token(self, token_str):
        if not token_str:
            return False, None
        token_str = token_str.strip()
        with _lock:
            for t in self.tokens:
                if t.get("status") == "active" and t.get("token") == token_str:
                    t["last_used_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    t["use_count"] = t.get("use_count", 0) + 1
                    self._save_unlocked()
                    return True, t.get("name", "Unknown")
        return False, None

    def create_token(self, name):
        with _lock:
            new_id = "tok_" + secrets.token_hex(6)
            new_val = "mt5_live_" + secrets.token_hex(16)
            item = {
                "id": new_id,
                "name": name.strip() if name else f"Token-{new_id}",
                "token": new_val,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_used_at": None,
                "use_count": 0,
                "status": "active"
            }
            self.tokens.append(item)
            self._save_unlocked()
            return item

    def regenerate_token(self, token_id):
        with _lock:
            for t in self.tokens:
                if t.get("id") == token_id:
                    t["token"] = "mt5_live_" + secrets.token_hex(16)
                    t["last_used_at"] = None
                    self._save_unlocked()
                    return t
        return None

    def revoke_token(self, token_id):
        with _lock:
            for t in self.tokens:
                if t.get("id") == token_id:
                    t["status"] = "revoked"
                    self._save_unlocked()
                    return True
        return False

    def delete_token(self, token_id):
        with _lock:
            before = len(self.tokens)
            self.tokens = [t for t in self.tokens if t.get("id") != token_id]
            if len(self.tokens) < before:
                self._save_unlocked()
                return True
        return False

token_manager = TokenManager()
