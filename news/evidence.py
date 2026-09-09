"""evidence — 事件证据系统 + 事实状态（纯规则, AI OFF 可用）"""
import re, unicodedata
from . import db as dbm
from .migrate_ext import ensure

MULTI_SUFFIX = ("co.jp", "com.cn", "co.uk", "com.au", "com.br", "com.tw", "co.kr", "com.hk", "org.cn")

def domain_of(url):
    if not url:
        return None
    host = re.sub(r"^[a-zA-Z]+://", "", url).split("/")[0].split("@")[-1].split(":")[0].lower()
    host = re.sub(r"^www\d?\.", "", host)
    parts = host.split(".")
    for suf in MULTI_SUFFIX:
        if host.endswith("." + suf):
            return ".".join(parts[-(len(suf.split(".")) + 1):])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host or None

def _norm_title(t):
    t = unicodedata.normalize("NFKC", t or "").lower()
    return re.sub(r"[^\w ]", "", t).strip()

def rebuild_evidence(con, story_id):
    con.execute("DELETE FROM event_evidence WHERE story_id=?", (story_id,))
    rows = con.execute("""SELECT a.id, a.url, a.title, a.published_at, s.slug, s.source_type, s.tier, s.site_url
                          FROM articles a JOIN sources s ON s.id=a.source_id
                          WHERE a.story_id=?""", (story_id,)).fetchall()
    by_dom, by_title = {}, {}
    for r in rows:
        dom = domain_of(r["url"] or r["site_url"] or r["slug"])
        key = (r["slug"], dom)
        if key in by_dom:
            continue
        by_dom[key] = r
        nt = _norm_title(r["title"])
        if len(nt) >= 20:
            by_title.setdefault(nt, []).append(r)
    # 转载识别: 同标题跨域 → 最早发布者 = original
    originals = set()
    for group in by_title.values():
        doms = {domain_of(r["url"] or r["site_url"] or r["slug"]) for r in group}
        if len(doms) > 1:
            group.sort(key=lambda r: r["published_at"] or "9999")
            originals.add(group[0]["id"])
    tier_c = {"community", "social", "video", "podcast", "blog"}
    indep, indep_fact = set(), set()
    for (slug, dom), r in by_dom.items():
        is_orig = 1 if r["id"] in originals or len(by_title.get(_norm_title(r["title"]), [])) <= 1 else 0
        con.execute("""INSERT OR IGNORE INTO event_evidence(story_id,article_id,domain,source_type,tier,is_original,at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (story_id, r["id"], dom, r["source_type"], r["tier"], is_orig, dbm.utcnow()))
        if is_orig:
            indep.add(dom)
            if r["tier"] not in ("C",) and r["source_type"] not in tier_c:
                indep_fact.add(dom)
    n_indep = len(indep)
    con.execute("UPDATE stories SET independent_source_count=? WHERE id=?", (n_indep, story_id))
    return n_indep, len(by_dom)

def compute_status(con, story_id):
    rows = con.execute("""SELECT e.tier, e.source_type, e.is_original FROM event_evidence e WHERE e.story_id=?""",
                       (story_id,)).fetchall()
    if not rows:
        return "UNVERIFIED"
    a = con.execute("SELECT fact_status FROM stories WHERE id=?", (story_id,)).fetchone()
    if a and a["fact_status"] in ("DISPUTED", "CORRECTED", "FALSE"):
        return a["fact_status"]          # 人工状态优先, 不被自动降级
    if any(r["tier"] == "A" and r["is_original"] for r in rows):
        return "OFFICIAL_CONFIRMED"
    indep_fact = {domain_of("x") for _ in ()}
    n = con.execute("SELECT COUNT(DISTINCT domain) FROM event_evidence WHERE story_id=? AND is_original=1 AND tier<>'C'", (story_id,)).fetchone()[0]
    if n >= 2:
        return "CORROBORATED"
    if n == 1:
        return "SINGLE_SOURCE"
    return "UNVERIFIED"

def set_fact_status(con, story_id, status, reason):
    con.execute("INSERT INTO story_fact_history(story_id, fact_status, reason, at) VALUES(?,?,?,?)",
                (story_id, status, reason, dbm.utcnow()))
    con.execute("UPDATE stories SET fact_status=?, fact_status_updated_at=? WHERE id=?",
                (status, dbm.utcnow(), story_id))

def refresh_story(con, story_id):
    try:
        rebuild_evidence(con, story_id)
        s = compute_status(con, story_id)
        cur = con.execute("SELECT fact_status FROM stories WHERE id=?", (story_id,)).fetchone()
        if cur is None or cur["fact_status"] != s:
            set_fact_status(con, story_id, s, "auto")
        return s
    except Exception:
        con.rollback() if hasattr(con, "rollback") else None
        return None

def refresh_active(con, limit=400):
    ids = [r[0] for r in con.execute("SELECT id FROM stories WHERE status='active' ORDER BY last_updated DESC LIMIT ?",
                                     (limit,)).fetchall()]
    out = {}
    for sid in ids:
        s = refresh_story(con, sid)
        if s:
            out[s] = out.get(s, 0) + 1
    con.commit()
    return out
