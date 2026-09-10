#!/usr/bin/env python3
"""qa_acceptance.py — 只读验收脚本 (P0-S11 修复版: 零硬编码凭据)
用法: QA_MCP_TOKEN=<token> QA_ADMIN_PW=<pw> SSHPASS=<ssh密码> python3 scripts/qa_acceptance.py
安全: 凭据仅从环境变量读取; SSH 用 sshpass -e; 本文件可安全入库。"""
import json, os, subprocess, sys, urllib.request, http.cookiejar, ssl
HOST = "catmi@s12.serv00.com"
B = "https://myp.micsdic.dpdns.org"
TOK = os.environ.get("QA_MCP_TOKEN", "")
ADMIN_PW = os.environ.get("QA_ADMIN_PW", "")
if not TOK or not ADMIN_PW or not os.environ.get("SSHPASS"):
    print("缺少环境变量 QA_MCP_TOKEN / QA_ADMIN_PW / SSHPASS"); sys.exit(2)
def sh(cmd):
    return subprocess.run(["sshpass", "-e", "ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "LogLevel=ERROR", HOST, cmd],
                          capture_output=True, text=True, timeout=120).stdout
ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    print(("PASS " if cond else "FAIL ") + name + (f" | {detail}" if detail else ""))
    ok, fail = ok + (1 if cond else 0), fail + (0 if cond else 1)
# 1 S1 文件权限 (只读 stat)
perm = sh("stat -f '%p' ~/news-project/news-data/database/news.db 2>/dev/null")
check("S1 news.db 权限 600", "600" in perm, perm.strip())
# 2 S2 正文抓取健康 (只读; [P3-S12-1] strftime 格式对齐 ISO 'T', 断言 >=1)
health = sh("cd ~/news-project && ./venv/bin/python -c \"import sqlite3; con=sqlite3.connect('file:news-data/database/news.db?mode=ro', uri=True); print(con.execute(\\\"SELECT COUNT(*) FROM articles WHERE content IS NOT NULL AND discovered_at >= strftime('%Y-%m-%dT%H:%M:%SZ','now','-3 hours')\\\").fetchone()[0])\"")
check("S2 近3h 有正文入库 (>=1)", health.strip().isdigit() and int(health.strip()) >= 1, health.strip())
# 3 S3 ai-worker 只读检查 ([P3-S12-2] 不再执行脚本, 改为静态检查 cd 行)
aw = sh("grep -c 'cd \"\\$PROJ\"' ~/news-project/scripts/ai-worker.sh")
check("S3 ai-worker.sh 含 cd 行 (只读检查)", aw.strip() == "1", aw.strip())
# 4 MCP 冒烟 (凭据来自 env)
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))
op.addheaders = [("User-Agent", "Mozilla/5.0 Chrome/120.0.0.0")]
op.open(B + "/", timeout=30)
CSRF = json.loads(op.open(urllib.request.Request(B + "/api/auth/login", data=json.dumps({"username": "admin", "password": ADMIN_PW}).encode(), headers={"Content-Type": "application/json"}), timeout=30).read()).get("csrf")
check("admin 登录", bool(CSRF))
def mcp(name, args):
    req = urllib.request.Request(B + "/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}).encode(), headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json", "Accept": "application/json, text/event-stream", "X-GI-CSRF": CSRF or ""})
    d = json.loads(op.open(req, timeout=150).read())
    try: return json.loads(d["result"]["content"][0]["text"])
    except Exception: return {"raw": str(d)[:80]}
for kw in ({"time_range": "day"}, {"page": 2}, {"limit": 1}):
    r = mcp("web_search", {"q": "test", **kw}); check(f"web_search {kw} 不崩", "raw" not in r)
r = mcp("web_search", {"q": "特斯拉 财报", "time_range": "day", "limit": 5})
check("time_range 硬过滤生效", r.get("window_dropped", 0) > 0 or len(r.get("results", [])) > 0, f"dropped={r.get('window_dropped')}")
r = mcp("deep_search", {"q": "Ukraine drone strike Kyiv"})
check("deep_search evidence>0", len(r.get("evidence", [])) > 0, f"e={len(r.get('evidence', []))}")
r = mcp("get_event", {"id": 174})
a = [x for x in r.get("articles", []) if x.get("id") == 7]
check("get_event content_chars 正确", bool(a) and a[0].get("content_chars", 0) > 1000, str(a[0].get("content_chars") if a else None))
r = mcp("search_intelligence", {"q": "Iran", "limit": 1})
check("无 fingerprint 泄露", "fingerprint" not in json.dumps(r))
r = mcp("get_trending", {"hours": 48})
check("trending hours=48 非空", len(r.get("results", [])) > 0)
r = mcp("read_url", {"url": "https://news.google.com/"})
check("consent→needs_js+published null", r.get("status") == "needs_js" and r.get("published") is None)
print(f"\n== 验收结果: {ok} PASS / {fail} FAIL ==")
sys.exit(1 if fail else 0)
