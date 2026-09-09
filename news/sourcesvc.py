#!/usr/bin/env python3
"""news.sourcesvc — 源注册表: 种子导入/健康统计"""
import json, pathlib

from . import db as dbm

def seed(con, path):
    """从 JSON 导入源（slug 冲突时更新抓取字段，保留运营状态）"""
    data = json.loads(pathlib.Path(path).read_text())
    n = u = 0
    for s in data:
        slug = s["slug"]
        if con.execute("SELECT 1 FROM sources WHERE slug=?", (slug,)).fetchone():
            con.execute("""UPDATE sources SET name=?, kind=?, feed_url=?, site_url=?, category=?,
                           language=?, country=?, priority=?, poll_seconds=?, adapter=?,
                           disabled=0, disabled_reason=NULL WHERE slug=?""",
                        (s["name"], s.get("kind", "rss"), s["feed_url"], s.get("site_url"),
                         s.get("category", "general"), s.get("language", "en"), s.get("country"),
                         s.get("priority", 1.0), s.get("poll_seconds", 900), s.get("adapter"), slug))
            u += 1
        else:
            con.execute("""INSERT INTO sources(slug,name,kind,feed_url,site_url,category,language,
                           country,priority,poll_seconds,adapter,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (slug, s["name"], s.get("kind", "rss"), s["feed_url"], s.get("site_url"),
                         s.get("category", "general"), s.get("language", "en"), s.get("country"),
                         s.get("priority", 1.0), s.get("poll_seconds", 900), s.get("adapter"), dbm.utcnow()))
            n += 1
    con.commit()
    return {"inserted": n, "updated": u, "total": len(data)}

def health(con):
    return {
        "sources_total": con.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
        "sources_active": con.execute("SELECT COUNT(*) FROM sources WHERE disabled=0").fetchone()[0],
        "sources_disabled": con.execute("SELECT COUNT(*) FROM sources WHERE disabled=1").fetchone()[0],
        "articles_total": con.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
        "articles_24h": con.execute("SELECT COUNT(*) FROM articles WHERE discovered_at>=?",
                                    (dbm.iso_ago(hours=24),)).fetchone()[0],
        "articles_with_content": con.execute(
            "SELECT COUNT(*) FROM articles WHERE content IS NOT NULL").fetchone()[0],
        "stories_active": con.execute("SELECT COUNT(*) FROM stories WHERE status='active'").fetchone()[0],
        "images_total": con.execute("SELECT COUNT(*) FROM images WHERE purged_at IS NULL").fetchone()[0],
        "tasks_pending": con.execute("SELECT COUNT(*) FROM crawl_tasks WHERE state='pending'").fetchone()[0],
        "tasks_failed": con.execute("SELECT COUNT(*) FROM crawl_tasks WHERE state='failed'").fetchone()[0],
        "errors_24h": con.execute("SELECT COUNT(*) FROM crawl_errors WHERE at>=?",
                                  (dbm.iso_ago(hours=24),)).fetchone()[0],
    }

# ---------- Source Intelligence 扩展（tier/quality, 规则可解释） ----------
TIER_OF = {"official": "A", "government": "A", "regulator": "A", "central_bank": "A",
           "research": "A", "statistics": "A", "wire_service": "A",
           "professional_media": "B", "regional_media": "B", "financial": "B",
           "corporate": "B", "legal": "B",
           "community": "C", "social": "C", "video": "C", "podcast": "C", "blog": "C"}
WIRE_SLUGS = ("reuters", "bbc", "afp", "ap", "yonhap", "tass", "nhk", "dw", "aljazeera", "cna")
OFFICIAL_HINTS = ("gov", "who.int", "un.org", "nasa", "imf", "ecb", "fed", "boj", "statistics", "census")
COMMUNITY_HINTS = ("reddit", "hnews", "github", "youtube", "hnrss", "phoronix", "krebsonsecurity")

def classify(s):
    """(source_type, tier) — slug/域名规则映射"""
    slug = (s.get("slug") or "").lower()
    st = s.get("source_type")
    if not st:
        if any(k in slug for k in OFFICIAL_HINTS):
            st = "official"
        elif any(k in slug for k in COMMUNITY_HINTS):
            st = "community"
        elif any(k in slug for k in WIRE_SLUGS):
            st = "wire_service"
        else:
            st = "regional_media"
    return st, TIER_OF.get(st, "B")

def score_source(s):
    """0-100, 5 分项各 0-20, 全规则（docs/SOURCE_QUALITY.md）"""
    st, tier = classify(s)
    authority = {"A": 20, "B": 14, "C": 6}[tier]
    kind = s.get("kind", "rss")
    independence = 4 if st == "community" and "reddit" in (s.get("slug") or "") else \
                   12 if tier == "B" else 20
    original = {"official": 20, "research": 20, "wire_service": 18, "professional_media": 14,
                "regional_media": 12, "financial": 14, "community": 4, "social": 4, "video": 6,
                "blog": 10}.get(st, 12)
    poll = int(s.get("poll_seconds") or 900)
    update = 20 if poll <= 900 else 12 if poll <= 1800 else 6
    https = (s.get("feed_url") or "").startswith("https")
    tech = 20 if https else 10
    return {"score": authority + independence + original + update + tech,
            "components": {"authority": authority, "independence": independence,
                           "original_reporting": original, "update_frequency": update,
                           "technical_reliability": tech},
            "source_type": st, "tier": tier}

def backfill(con):
    """为现有 sources 全量打 source_type/tier/quality_score, verification_status='active'"""
    n = 0
    for r in con.execute("SELECT id, slug, name, kind, feed_url, site_url, category, language, country, priority, poll_seconds, source_type FROM sources").fetchall():
        d = {k: r[k] for k in r.keys()}
        st, tier = classify(d)
        sc = score_source({**d, "source_type": st})
        con.execute("UPDATE sources SET source_type=?, tier=?, quality_score=?, verification_status='active' WHERE id=?",
                    (st, tier, sc["score"], r["id"]))
        n += 1
    con.commit()
    return n
