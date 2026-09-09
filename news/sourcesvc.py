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
