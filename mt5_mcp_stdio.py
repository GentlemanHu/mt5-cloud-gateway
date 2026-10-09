#!/usr/bin/env python3
import sys
import json
import os
import argparse
import urllib.request
import urllib.error

def parse_args():
    parser = argparse.ArgumentParser(description="MT5 Gateway Model Context Protocol (MCP) Stdio Client")
    parser.add_argument(
        "--url", "-u",
        default=os.environ.get("MT5_GATEWAY_URL", "http://localhost:18812"),
        help="MT5 Gateway base URL (default: http://localhost:18812 or MT5_GATEWAY_URL env)"
    )
    parser.add_argument(
        "--token", "-t",
        default=os.environ.get("MT5_GATEWAY_TOKEN", ""),
        help="MT5 API Bearer access token (default: MT5_GATEWAY_TOKEN env)"
    )
    return parser.parse_known_args()

def main():
    args, _ = parse_args()
    gateway_url = args.url.rstrip('/')
    token = args.token.strip()

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                req = json.loads(line)
            except Exception:
                continue

            req_id = req.get("id") if isinstance(req, dict) else None

            # Token validation
            if not token:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32002,
                        "message": "Missing MT5_GATEWAY_TOKEN. Provide via --token <TOKEN> or MT5_GATEWAY_TOKEN environment variable."
                    }
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
                continue

            # Forward JSON-RPC request to Streamable HTTP MCP endpoint
            url = f"{gateway_url}/mcp?token={token}"
            post_data = json.dumps(req).encode('utf-8')
            http_req = urllib.request.Request(
                url,
                data=post_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "MT5-MCP-Stdio-Client/1.1"
                }
            )

            try:
                with urllib.request.urlopen(http_req, timeout=30) as resp:
                    resp_bytes = resp.read()
                    resp_str = resp_bytes.decode('utf-8').strip()
                    if resp_str:
                        sys.stdout.write(resp_str + "\n")
                        sys.stdout.flush()
            except urllib.error.HTTPError as e:
                err_body = e.read().decode('utf-8', errors='ignore')
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32000,
                        "message": f"HTTP {e.code}: {err_body}"
                    }
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32000,
                        "message": f"Network/Gateway Connection Error: {str(e)}"
                    }
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()

        except KeyboardInterrupt:
            break
        except Exception as e:
            sys.stderr.write(f"Stdio MCP loop error: {e}\n")
            sys.stderr.flush()

if __name__ == '__main__':
    main()
