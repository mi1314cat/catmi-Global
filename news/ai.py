"""ai — FreeLLM Auto 情报增强（事件级, 缓存, 降级安全; 采集永不被 AI 阻塞）"""
import hashlib, json, re, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from . import db as dbm
from .migrate_ext import ensure

PROMPT_VERSION = "v1"
COOLDOWN_S = 600          # 失败冷却, 期间 RULE_ONLY
TASKS = {"HIGH": ["summary_entities"], "CRITICAL": ["summary_entities", "timeline_conflicts"]}

# ---------- 配置（DB meta 优先, env 兜底; Key 永不进日志/Git/前端） ----------
def cfg(con):
    def m(k):
        r = con.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
        return r[0] if r else None
    import os
    return {"url": (m("ai_freellm_url") or os.environ.get("FREELLM_API_URL", "")).rstrip("/"),
            "key": m("ai_freellm_key") or os.environ.get("FREELLM_API_KEY", ""),
            "model": m("ai_freellm_model") or os.environ.get("FREELLM_MODEL", "auto"),
            "enabled": (m("ai_enabled") or "1") == "1"}

# ---------- 规则重要度（不靠 AI） ----------
CRIT_KW = ("war", "invasion", "strikes", "sanction", "coup", "earthquake", "tsunami", "nuclear",
           "pandemic", "outbreak", "bankrupt", "default", "rate decision", "rate cut", "rate hike",
           "data breach", "ransomware", "explosion", "missile", "ceasefire", "martial")
HIGH_KW = ("election", "merger", "acquisition", "chip", "semiconductor", "ai ", "regulat", "central bank",
           "opec", "gdp", "inflation", "summit", "treaty", "ban", "lawsuit", "indict")

def intel_importance(con, story_id):
    r = con.execute("""SELECT s.title, s.fact_status, s.independent_source_count,
        (SELECT COUNT(*) FROM articles a WHERE a.story_id=s.id) AS arts,
        (SELECT COUNT(*) FROM event_evidence e JOIN sources s2 ON s2.id=e.article_id IS NULL) FROM stories s WHERE s.id=?""", (story_id,)).fetchone() if False else \
        con.execute("SELECT title, fact_status, independent_source_count, (SELECT COUNT(*) FROM articles WHERE story_id=?) AS arts FROM stories WHERE id=?", (story_id, story_id)).fetchone()
    title = (r["title"] or "").lower()
    indep = r["independent_source_count"] or 0
    arts = r["arts"]
    off = con.execute("""SELECT COUNT(*) FROM event_evidence e WHERE e.story_id=? AND e.tier='A' AND e.is_original=1""", (story_id,)).fetchone()[0]
    wire = con.execute("""SELECT COUNT(DISTINCT e.domain) FROM event_evidence e WHERE e.story_id=? AND e.source_type IN ('wire_service','professional_media') AND e.is_original=1""", (story_id,)).fetchone()[0]
    score, why = 0, []
    if any(k in title for k in CRIT_KW): score += 3; why.append("crit_keyword")
    if any(k in title for k in HIGH_KW): score += 1; why.append("high_keyword")
    if indep >= 4: score += 3; why.append(f"indep={indep}")
    elif indep >= 2: score += 1; why.append(f"indep={indep}")
    if off >= 1: score += 2; why.append("official_confirmed")
    if wire >= 2: score += 1; why.append(f"wire={wire}")
    if arts >= 6: score += 1; why.append(f"arts={arts}")
    lvl = "LOW" if score <= 0 else "NORMAL" if score == 1 else "NOTABLE" if score == 2 else "HIGH" if score <= 4 else "CRITICAL"
    return lvl, ";".join(why)

def enqueue(con, limit=300):
    """入队: trending 等级(lowercase, UI 层) + 情报规则(独立来源/官方/关键词) 组合。
    stories.importance 归 trending 模块所有, AI 层不覆盖。"""
    q = {}
    rows = con.execute("""SELECT s.id, s.importance AS t_imp, s.title, s.fact_status, s.independent_source_count,
        (SELECT COUNT(*) FROM articles WHERE story_id=s.id) AS arts
        FROM stories s WHERE s.status='active'
        AND NOT EXISTS(SELECT 1 FROM ai_queue q WHERE q.story_id=s.id)
        ORDER BY s.last_updated DESC LIMIT ?""", (limit,)).fetchall()
    for r in rows:
        lvl, why = intel_importance(con, r["id"])
        t = (r["t_imp"] or "").lower()
        if t == "major":
            lvl = "CRITICAL"; why = "trending:major+" + why
        elif t == "high" and lvl in ("LOW", "NORMAL"):
            lvl = "HIGH"; why = "trending:high"
        if lvl in ("NOTABLE", "HIGH", "CRITICAL"):
            pri = {"NOTABLE": 1, "HIGH": 2, "CRITICAL": 3}[lvl]
            tasks = TASKS.get(lvl, ["summary_entities"])
            for tk in tasks:
                con.execute("INSERT OR IGNORE INTO ai_queue(story_id, task_type, priority, created_at) VALUES(?,?,?,?)",
                            (r["id"], tk, pri, dbm.utcnow()))
            q[lvl] = q.get(lvl, 0) + 1
    con.commit()
    return q

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
    with urlopen(req, timeout=150) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"], d.get("model", c["model"])

def _cached(con, ih, task, content, model):
    con.execute("""INSERT OR IGNORE INTO ai_cache(input_hash, task_type, prompt_version, model, response, created_at)
                   VALUES(?,?,?,?,?,?)""", (ih, task, PROMPT_VERSION, model, content, dbm.utcnow()))

def worker(con, max_items=3):
    """低并发处理队列; 失败冷却→RULE_ONLY; 采集/搜索不受影响"""
    c = cfg(con)
    if not c["enabled"] or not c["url"]:
        return {"skipped": "ai_disabled_or_unconfigured"}
    cd = con.execute("SELECT value FROM meta WHERE key='ai_cooldown_until'").fetchone()
    if cd and cd[0] > dbm.utcnow():
        return {"skipped": "cooldown(RULE_ONLY)"}
    items = con.execute("""SELECT id, story_id, task_type FROM ai_queue WHERE status='pending'
                           ORDER BY priority DESC, id LIMIT ?""", (max_items,)).fetchall()
    done = fail = cache_hit = 0
    for it in items:
        try:
            s = con.execute("SELECT title FROM stories WHERE id=?", (it["story_id"],)).fetchone()
            arts = con.execute("""SELECT a.title, a.url, s.slug FROM articles a JOIN sources s ON s.id=a.source_id
                                  WHERE a.story_id=? ORDER BY a.published_at LIMIT 8""", (it["story_id"],)).fetchall()
            src = "\n".join(f"- {a['title']} ({a['slug']}) {a['url']}" for a in arts)
            ask = ("你是情报分析助手。对以下事件输出严格 JSON: {\"summary\":\"3句中文摘要\",\"entities\":[\"实体\"],"
                   "\"timeline\":[{\"time\":\"...\",\"what\":\"...\"}],\"conflicts\":[\"信息冲突点(无则空)\"]}。"
                   f"\n事件: {s['title']}\n报道:\n{src}")
            ih = hashlib.sha256((ask).encode()).hexdigest()
            row = con.execute("SELECT response FROM ai_cache WHERE input_hash=? AND task_type=? AND prompt_version=? AND model=?",
                              (ih, it["task_type"], PROMPT_VERSION, c["model"])).fetchone()
            if row:
                content, model_used, cache_hit = row["response"], c["model"], cache_hit + 1
            else:
                content, model_used = _call(con, ask, c["model"])
                if content is None:
                    raise RuntimeError("unconfigured")
                _cached(con, ih, it["task_type"], content, model_used)
            j = json.loads(re.search(r"\{.*\}", content, re.S).group(0))
            con.execute("""UPDATE stories SET ai_enhanced=1, ai_model=?, ai_prompt_version=?, ai_at=?,
                           ai_summary=?, ai_entities=?, ai_timeline=? WHERE id=?""",
                        (model_used, PROMPT_VERSION, dbm.utcnow(), j.get("summary"),
                         json.dumps(j.get("entities", []), ensure_ascii=False),
                         json.dumps(j.get("timeline", []), ensure_ascii=False), it["story_id"]))
            con.execute("UPDATE ai_queue SET status='done', processed_at=? WHERE id=?", (dbm.utcnow(), it["id"]))
            done += 1
        except (HTTPError, URLError, RuntimeError, json.JSONDecodeError, KeyError, OSError) as e:
            code = getattr(e, "code", None)
            fail += 1
            con.execute("UPDATE ai_queue SET attempts=attempts+1, status=CASE WHEN attempts>=2 THEN 'failed' ELSE status END, last_error=? WHERE id=?",
                        (str(e)[:150], it["id"]))
            if code == 429 or "timeout" in str(e).lower() or "timed out" in str(e).lower():
                con.execute("INSERT INTO meta(key,value) VALUES('ai_cooldown_until',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                            (dbm.iso_ago(hours=-0.17),))  # 10min 后
    con.commit()
    return {"done": done, "failed": fail, "cache_hit": cache_hit, "queue_left": con.execute("SELECT COUNT(*) FROM ai_queue WHERE status='pending'").fetchone()[0]}
