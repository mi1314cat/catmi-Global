#!/usr/bin/env python3
"""ai-test.py — 管理后台"测试连接"执行器: 最小 FreeLLM Auto 调用"""
import json, sys, time
sys.path.insert(0, "/usr/home/catmi/news-project")
from news import db as dbm
from news import ai
con = dbm.connect(); con.execute("PRAGMA busy_timeout=8000")
t0 = time.time()
try:
    out = ai._call(con, '回复 JSON: {"ok":1}', "auto")
    c, model = out[0], out[1]
    print(json.dumps({"ok": c is not None, "model": model, "latency": round(time.time() - t0, 1)}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)[:150], "latency": round(time.time() - t0, 1)}))
con.close()
