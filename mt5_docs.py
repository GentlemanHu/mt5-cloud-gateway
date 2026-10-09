import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOGIN_PAGE_HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>MT5 控制台 · 安全登录</title><style>body{background:#080c14;color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}.box{background:rgba(16,23,38,0.92);border:1px solid rgba(0,229,255,0.3);border-radius:16px;padding:36px;width:90%;max-width:380px;text-align:center;box-shadow:0 16px 40px rgba(0,0,0,0.8)}h2{margin-bottom:8px;font-size:20px}p{color:#94a3b8;font-size:13px;margin-bottom:24px}input{width:100%;padding:12px;border-radius:8px;background:#04060a;border:1px solid rgba(255,255,255,0.15);color:#fff;font-size:15px;text-align:center;margin-bottom:16px;outline:none;box-sizing:border-box}input:focus{border-color:#00e5ff}button{width:100%;padding:12px;border-radius:8px;background:linear-gradient(135deg,#00e5ff,#0088cc);color:#080c14;font-weight:700;font-size:14px;border:none;cursor:pointer}button:hover{opacity:0.95}.err{color:#ff3d71;font-size:13px;margin-top:12px;display:none}</style></head><body><div class="box"><div style="font-size:36px;margin-bottom:12px">🔐</div><h2>MT5 管理控制台</h2><p>请输入管理员全局访问密码进入系统</p><form onsubmit="doLogin(event)"><input type="password" id="pwd" placeholder="请输入管理员密码" required autofocus><button type="submit">安全登入</button><div id="errMsg" class="err">访问密码错误，请重试</div></form></div><script>async function doLogin(e){e.preventDefault();const val=document.getElementById('pwd').value.trim();const res=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:val})});if(res.ok){location.href='/'}else{document.getElementById('errMsg').style.display='block'}}</script></body></html>"""

def get_docs_html():
    p = os.path.join(BASE_DIR, "docs.html")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f.read()
    return b"<h1>Documentation file not found</h1>"

def get_llms_txt():
    p = os.path.join(BASE_DIR, "llms.txt")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f.read()
    return b"# MT5 Gateway\nDocumentation not found."

def get_openapi_json():
    p = os.path.join(BASE_DIR, "openapi.json")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f.read()
    return b'{"openapi": "3.1.0", "info": {"title": "MT5 Gateway"}}'
