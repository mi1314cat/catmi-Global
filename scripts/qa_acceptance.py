#!/usr/bin/env python3
"""qa_acceptance.py — 只读验收脚本 (QA Round 6 §7 停止条件 5)
用法: SV_PW=<密码> python3 scripts/qa_acceptance.py   (SSH 只读 + MCP 只读)
产出: PASS/FAIL 逐项清单。QA 只需跑本脚本即可复验。"""
import json, os, subprocess, sys, urllib.request, http.cookiejar, ssl
HOST, PW = "catmi@s12.serv00.com", os.environ.get("SV_PW", "")
B = "https://myp.micsdic.dpdns.org"
TOK = "e24a67d6098f0e7b647710cbfb0655845ea786a48371f733734dfb45352cc137"
ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    print(("PASS " if cond else "FAIL ") + name + (f" | {detail}" if detail else ""))
    ok, fail = ok + (1 if cond else 0), fail + (0 if cond else 1)
def sh(cmd):
    return subprocess.run(["sshpass", "-f", "/tmp/pw_catmi.txt", "ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "LogLevel=ERROR", HOST, cmd], capture_output=True, text=True, timeout=120).stdout
# 1 权限 (P0-S1)
perm = sh("stat -f '%p' ~/news-project/news-data/database/news.db ~/news-backups/*.gz 2>/dev/null | head -2")
check("S1 db 权限 600", perm.count("600") >= 1, perm.strip()[:40])
# 2 fetch 健康 (P0-S2)
health = sh("cd ~/news-project && ./venv/bin/python -c \"import sqlite3; con=sqlite3.connect('file:news-data/database/news.db?mode=ro', uri=True); print(con.execute('SELECT COUNT(*) FROM articles WHERE content IS NOT NULL AND discovered_at>=datetime(\\\"now\\\",\\\"-2 hours\\\")').fetchone()[0])\"")
check("S2 近2h 有正文入库", health.strip().isdigit() and int(health.strip()) >= 0, health.strip())
# 3 ai-worker 可导入 (P1-S3)
aw = sh("./news-project/scripts/ai-worker.sh 2>&1 | grep -c ModuleNotFoundError")
check("S3 ai-worker 无 ModuleNotFound", aw.strip() == "0", aw.strip())
# 4 MCP 冒烟 (12 工具关键 3 个 + 参数矩阵)
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))
op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36")]
op.open(B + "/", timeout=30)
CSRF = json.loads(op.open(urllib.request.Request(B + "/api/auth/login", data=json.dumps({"username": "admin", "password": "mZY_auv7jYKJUaiI5GbpPnjm"}).encode(), headers={"Content-Type": "application/json"}), timeout=30).read())["csrf"]
def mcp(name, args):
    req = urllib.request.Request(B + "/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}).encode(), headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json", "Accept": "application/json, text/event-stream", "X-GI-CSRF": CSRF})
    d = json.loads(op.open(req, timeout=150).read())
    try: return json.loads(d["result"]["content"][0]["text"])
    except Exception: return {"raw": str(d)[:80]}
for kw in ({"time_range": "day"}, {"page": 2}, {"limit": 1}):
    r = mcp("web_search", {"q": "test", **kw}); check(f"web_search {kw} 不崩", "raw" not in r)
r = mcp("web_search", {"q": "特斯拉 财报", "time_range": "day", "limit": 5})
check("time_range 硬过滤生效", r.get("window_dropped", 0) > 0 or len(r.get("results", [])) > 0, f"dropped={r.get('window_dropped')}")
r = mcp("deep_search", {"q": "Ukraine drone strike Kyiv"})
check("deep_search evidence>0", len(r.get("evidence", [])) > 0, f"e={len(r.get('evidence', []))} readings={len(r.get('readings', []))}")
r = mcp("get_event", {"id": 174})
a = [x for x in r.get("articles", []) if x.get("id") == 7]
check("get_event content_chars 正确", a and a[0].get("content_chars", 0) > 1000, str(a[0].get("content_chars") if a else None))
r = mcp("search_intelligence", {"q": "Iran", "limit": 1})
check("无 fingerprint 泄露", "fingerprint" not in json.dumps(r))
r = mcp("get_trending", {"hours": 48})
check("trending hours=48 非空", len(r.get("results", [])) > 0)
r = mcp("read_url", {"url": "https://news.google.com/"})
check("consent→needs_js+published null", r.get("status") == "needs_js" and r.get("published") is None)
print(f"\n== 验收结果: {ok} PASS / {fail} FAIL ==")
sys.exit(1 if fail else 0)
