"""ai — FreeLLM Auto 情报增强 v2: 队列吞吐/优先级/去重/过期/回压/降级（规则实现）"""
import hashlib, json, re, threading, time
from queue import Queue
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from . import db as dbm
from .migrate_ext import ensure

PROMPT_VERSION = "v1"
TASKS = {"NOTABLE": ["summary_entities"], "HIGH": ["summary_entities"],
         "CRITICAL": ["summary_entities", "timeline_conflicts"]}
TTL_H = {3: 6, 2: 12, 1: 24}              # CRITICAL 6h / HIGH 12h / NOTABLE 24h
CONCURRENCY = 2                            # 单进程有限 HTTP 并发（初始 2）
REQ_TIMEOUT = 90
BACKPRESSURE = 300                         # pending 超阈值 → 只保留 HIGH/CRITICAL 新任务

def cfg(con):
    def m(k):
        r = con.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
        return r[0] if r else None
    import os
    return {"url": (m("ai_freellm_url") or os.environ.get("FREELLM_API_URL", "")).rstrip("/"),
            "key": m("ai_freellm_key") or os.environ.get("FREELLM_API_KEY", ""),
            "model": m("ai_freellm_model") or os.environ.get("FREELLM_MODEL", "auto"),
            "enabled": (m("ai_enabled") or "1") == "1"}

CRIT_KW = ("war", "invasion", "strikes", "sanction", "coup", "earthquake", "tsunami", "nuclear",
           "pandemic", "outbreak", "bankrupt", "default", "rate cut", "rate hike", "data breach",
           "ransomware", "explosion", "missile", "ceasefire", "martial", "nuked", "bombs")
HIGH_KW = ("election", "merger", "acquisition", "chip", "semiconductor", "ai ", "regulat",
           "central bank", "opec", "gdp", "inflation", "summit", "treaty", "lawsuit", "indict")

def _rules(con, sid, t_imp=None):
    r = con.execute("""SELECT title, independent_source_count,
        (SELECT COUNT(*) FROM articles WHERE story_id=?) AS arts FROM stories WHERE id=?""", (sid, sid)).fetchone()
    if not r:
        return "LOW", "-"
    title = (r["title"] or "").lower()
    indep = r["independent_source_count"] or 0
    score = 0
    if any(k in title for k in CRIT_KW): score += 3
    if any(k in title for k in HIGH_KW): score += 1
    score += 3 if indep >= 4 else 1 if indep >= 2 else 0
    off = con.execute("SELECT COUNT(*) FROM event_evidence WHERE story_id=? AND tier='A' AND is_original=1", (sid,)).fetchone()[0]
    if off: score += 2
    if r["arts"] >= 6: score += 1
    lvl = "LOW" if score <= 0 else "NORMAL" if score == 1 else "NOTABLE" if score == 2 else "HIGH" if score <= 4 else "CRITICAL"
    # 事件速度: 30 分钟内新增独立来源
    vel = con.execute("SELECT COUNT(DISTINCT domain) FROM event_evidence WHERE story_id=? AND at >= ?",
                      (sid, dbm.iso_ago(hours=-0.5))).fetchone()[0]
    if vel >= 10: lvl = "CRITICAL"
    elif vel >= 5 and lvl in ("LOW", "NORMAL", "NOTABLE"): lvl = "HIGH"
    elif vel >= 3 and lvl in ("LOW", "NORMAL"): lvl = "NOTABLE"
    if (t_imp or "").lower() == "major":
        lvl = "CRITICAL"
    elif (t_imp or "").lower() == "high" and lvl in ("LOW", "NORMAL"):
        lvl = "HIGH"
    return lvl, f"indep={indep},vel={vel},off={off}"

def enqueue(con, limit=400):
    """入队（每 story+task 唯一; 带过期时间; 回压保护）"""
    rows = con.execute("""SELECT s.id, s.importance AS t_imp FROM stories s
        WHERE s.status='active' AND NOT EXISTS(SELECT 1 FROM ai_queue q WHERE q.story_id=s.id)
        ORDER BY s.last_updated DESC LIMIT ?""", (limit,)).fetchall()
    n_pend = con.execute("SELECT COUNT(*) FROM ai_queue WHERE status='pending'").fetchone()[0]
    q = {}
    for r in rows:
        lvl, why = _rules(con, r["id"], r["t_imp"])
        if lvl not in TASKS:
            continue
        if n_pend > BACKPRESSURE and lvl == "NOTABLE":
            continue                                  # 回压: 低价值不入队
        pri = {"NOTABLE": 1, "HIGH": 2, "CRITICAL": 3}[lvl]
        for tk in TASKS[lvl]:
            con.execute("""INSERT OR IGNORE INTO ai_queue(story_id, task_type, priority, created_at, expires_at)
                           VALUES(?,?,?,?, datetime('now', ?))""",
                        (r["id"], tk, pri, dbm.utcnow(), f'-{TTL_H[pri]} hours'))
            q[lvl] = q.get(lvl, 0) + 1
    con.commit()
    return q

def maintenance(con):
    """去重/过期/清理重复 pending/重算优先级 → 清理报告"""
    rep = {}
    rep["expired"] = con.execute("""UPDATE ai_queue SET status='expired'
        WHERE status='pending' AND expires_at IS NOT NULL AND expires_at < ?""", (dbm.utcnow(),)).rowcount
    rep["dedup"] = con.execute("""DELETE FROM ai_queue WHERE status='pending' AND id NOT IN
        (SELECT MIN(id) FROM ai_queue WHERE status='pending' GROUP BY story_id, task_type)""").rowcount
    # 重复 pending（同 story 多任务保留: CRITICAL 双任务是设计; 这里只清同任务重复, 已在上面）
    rep["deferred_reset"] = con.execute("""UPDATE ai_queue SET status='pending'
        WHERE status='deferred' AND attempts < 3 AND last_attempt_at < datetime('now','-30 minutes')""").rowcount
    # 队列压力: 清理低价值过期风险
    pend = con.execute("SELECT COUNT(*) FROM ai_queue WHERE status='pending'").fetchone()[0]
    rep["pending"] = pend
    con.commit()
    return rep

def _build_prompt(con, story_id, task):
    s = con.execute("SELECT title FROM stories WHERE id=?", (story_id,)).fetchone()
    arts = con.execute("""SELECT a.title, a.url, s.slug FROM articles a JOIN sources s ON s.id=a.source_id
                          WHERE a.story_id=? ORDER BY a.published_at LIMIT 8""", (story_id,)).fetchall()
    src = "\n".join(f"- {a['title']} ({a['slug']}) {a['url']}" for a in arts)
    base = ("你是情报分析助手。对以下事件输出严格 JSON: {\"summary\":\"3句中文摘要\",\"entities\":[\"实体\"],"
            f"\n事件: {s['title']}\n报道:\n{src}")
    if task == "timeline_conflicts":
        return base.replace("\"conflicts\"", "x") + ',"timeline":[{"time":"...","what":"..."}],"conflicts":["信息冲突点(无则空)"]}'
    return base + "}"

def _call(con, prompt, model):
    c = cfg(con)
    if not c["enabled"] or not c["url"] or not c["key"]:
        return None, "disabled_or_unconfigured"
    body = json.dumps({"model": c["model"], "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": 900, "temperature": 0.2}).encode()
    req = Request(c["url"] + "/chat/completions", data=body,
                  headers={"Authorization": f"Bearer {c['key']}", "Content-Type": "application/json",
                           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                           "Accept": "application/json"})
    t0 = time.time()
    with urlopen(req, timeout=REQ_TIMEOUT) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"], d.get("model", c["model"]), round(time.time() - t0, 1)

def _process_one(con, it):
    story_id, task = it["story_id"], it["task_type"]
    prompt = _build_prompt(con, story_id, task)
    ih = hashlib.sha256(prompt.encode()).hexdigest()
    c = cfg(con)
    row = con.execute("SELECT response FROM ai_cache WHERE input_hash=? AND task_type=? AND prompt_version=? AND model=?",
                      (ih, task, PROMPT_VERSION, c["model"])).fetchone()
    if row:
        content, model_used, lat, hit = row["response"], c["model"], 0.0, True
    else:
        out = _call(con, prompt, c["model"])
        content, model_used, lat = out[0], out[1], out[2]
        if content is None:
            raise RuntimeError("unconfigured")
        hit = False
    j = json.loads(re.search(r"\{.*\}", content, re.S).group(0))
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("""UPDATE stories SET ai_enhanced=1, ai_model=?, ai_prompt_version=?, ai_at=?,
                   ai_summary=COALESCE(ai_summary,?), ai_entities=COALESCE(ai_entities,?),
                   ai_timeline=COALESCE(ai_timeline,?) WHERE id=?""",
                (model_used, PROMPT_VERSION, dbm.utcnow(), j.get("summary"),
                 json.dumps(j.get("entities", []), ensure_ascii=False),
                 json.dumps(j.get("timeline", []) if isinstance(j.get("timeline"), list) else [], ensure_ascii=False),
                 story_id))
    if not hit:
        con.execute("""INSERT OR IGNORE INTO ai_cache(input_hash, task_type, prompt_version, model, response, created_at)
                       VALUES(?,?,?,?,?,?)""", (ih, task, PROMPT_VERSION, model_used, content, dbm.utcnow()))
    con.execute("UPDATE ai_queue SET status='done', processed_at=?, last_latency_s=? WHERE id=?", (dbm.utcnow(), lat, it["id"]))
    return lat, hit

def _fail(con, it, e):
    code = getattr(e, "code", None)
    msg = str(e)[:150]
    if code == 429:
        con.execute("UPDATE ai_queue SET status='deferred', attempts=attempts+1, last_error=?, last_attempt_at=? WHERE id=?",
                    (msg, dbm.utcnow(), it["id"]))
    elif code in (403,):
        con.execute("UPDATE ai_queue SET status='deferred', attempts=attempts+1, last_error=?, last_attempt_at=? WHERE id=?",
                    (msg, dbm.utcnow(), it["id"]))
    else:
        con.execute("UPDATE ai_queue SET attempts=attempts+1, last_error=?, last_attempt_at=? WHERE id=?", (msg, dbm.utcnow(), it["id"]))
    con.commit()

def worker(con, max_items=None):
    """单进程 + 有限并发 + 动态批量 + 每批重新抢占"""
    c = cfg(con)
    if not c["enabled"] or not c["url"]:
        return {"skipped": "ai_disabled_or_unconfigured"}
    rep = maintenance(con)
    pend = rep["pending"]
    if max_items is None:
        max_items = 4 if pend < 20 else 10 if pend < 50 else 15 if pend < 100 else 25 if pend < 300 else 40
    items = con.execute("""SELECT id, story_id, task_type, priority FROM ai_queue WHERE status='pending'
                           AND (expires_at IS NULL OR expires_at >= ?)
                           ORDER BY priority DESC, id LIMIT ?""", (dbm.utcnow(), max_items)).fetchall()
    done = failed = hits = 0
    lats = []
    work = Queue()
    for it in items:
        work.put(it)
    lock = threading.Lock()
    def run():
        nonlocal done, failed, hits
        mycon = dbm.connect()
        mycon.execute("PRAGMA busy_timeout=15000")
        while True:
            try:
                it = work.get_nowait()
            except Exception:
                return
            try:
                lat, hit = _process_one(mycon, it)
                with lock:
                    done += 1; hits += hit; lats.append(lat)
                mycon.commit()
            except (HTTPError, URLError, RuntimeError, json.JSONDecodeError, KeyError, OSError, Exception) as e:
                _fail(mycon, it, e)
                with lock:
                    failed += 1
            finally:
                work.task_done()
    ths = [threading.Thread(target=run) for _ in range(CONCURRENCY)]
    for t in ths: t.start()
    for t in ths: t.join()
    mycon2 = dbm.connect(); mycon2.execute("PRAGMA busy_timeout=15000")
    meta = {"ai_last_run": dbm.utcnow(), "ai_last_done": done, "ai_last_failed": failed,
            "ai_cache_hits": hits, "ai_pending": mycon2.execute("SELECT COUNT(*) FROM ai_queue WHERE status='pending'").fetchone()[0]}
    for k, v in meta.items():
        mycon2.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
    mycon2.commit(); mycon2.close()
    return {"done": done, "failed": failed, "cache_hit": hits, "maintenance": rep,
            "batch": len(items), "latency_avg": round(sum(lats)/len(lats), 1) if lats else None}
