#!/usr/bin/env python3
"""news.newsctl — 管道 CLI（cron 入口; 全部命令零 AI 依赖）
用法: venv/bin/python -m news.newsctl <cmd> [...]
采集: scan / fetch / images / cluster / trending / run
数据: search / latest / story / article / sources
运维: init-db seed-sources status doctor cleanup backup
"""
import argparse, gzip, json, pathlib, sqlite3, time

from . import config, db as dbm, search, sourcesvc
from .collector import scan
from .fetcher import Fetcher

def _con():
    con = dbm.connect(); dbm.init_schema(con); return con

def cmd_init_db(a):
    con = _con(); print(f"db ready: {config.DB_PATH} (schema v{dbm.SCHEMA_VERSION})")

def cmd_seed_sources(a):
    con = _con(); print(json.dumps(sourcesvc.seed(con, a.file), ensure_ascii=False))

def cmd_scan(a):
    con = _con(); f = Fetcher()
    try: print(json.dumps(scan(con, f, limit=a.limit, force=a.force), ensure_ascii=False))
    finally: f.close(); con.close()

def cmd_fetch(a):
    from . import extractor
    con = _con(); f = Fetcher()
    try: print(json.dumps(extractor.run(con, f, limit=a.limit), ensure_ascii=False))
    finally: f.close(); con.close()

def cmd_images(a):
    from . import images as images_mod
    con = _con(); f = Fetcher()
    try: print(json.dumps(images_mod.run(con, f, limit=a.limit), ensure_ascii=False))
    finally: f.close(); con.close()

def cmd_cluster(a):
    from . import stories
    con = _con(); print(json.dumps(stories.run(con, window_hours=a.window), ensure_ascii=False))

def cmd_trending(a):
    from . import trending as trending_mod
    con = _con()
    r = trending_mod.run(con, window_hours=a.window)
    r["top"] = [t["title"] for t in trending_mod.top(con, window_hours=a.window, limit=5)]
    print(json.dumps(r, ensure_ascii=False))

def cmd_cleanup(a):
    from . import retention
    con = _con()
    print(json.dumps(retention.run(con, force_emergency="emergency" if a.emergency else None),
                     ensure_ascii=False))

def cmd_run(a):
    """完整管道一轮（cron 主入口）: scan→fetch→images→cluster→trending，磁盘保护联动"""
    from . import extractor, images as images_mod, stories, trending as trending_mod
    from .images import monitor_level
    con = _con(); f = Fetcher()
    out = {"started": dbm.utcnow()}
    try:
        level = monitor_level(con)
        out["disk_level"] = level
        if level != "emergency":
            out["scan"] = scan(con, f, limit=getattr(a, "scan_limit", None))
            out["fetch"] = extractor.run(con, f, limit=config.FETCH_BATCH)
            out["images"] = images_mod.run(con, f, limit=config.IMAGE_BATCH) if config.IMAGES_ENABLED else {"skipped": "IMAGES_ENABLED=0 (只存 URL)"}
        else:
            out["skipped"] = "disk emergency — 仅清理模式"
        out["cluster"] = stories.run(con)
        try:
            from . import evidence as evidence_mod
            out["evidence"] = evidence_mod.refresh_active(con)
        except Exception as _e:
            out["evidence"] = {"error": str(_e)[:120]}
        try:
            from . import ai as ai_mod
            out["ai_importance"] = ai_mod.enqueue(con)
            out["ai_worker"] = ai_mod.worker(con, max_items=3)
        except Exception as _e:
            out["ai_worker"] = {"error": str(_e)[:120]}
        out["trending"] = trending_mod.run(con)
        out["finished"] = dbm.utcnow()
        dbm.meta_set(con, "last_run", out["finished"])
        print(json.dumps(out, ensure_ascii=False))
    finally:
        f.close(); con.close()

def cmd_status(a):
    con = _con()
    h = sourcesvc.health(con)
    lvl = __import__("news.images", fromlist=["monitor_level"]).monitor_level(con)
    h["disk_level"] = lvl
    q = con.execute("SELECT value FROM meta WHERE key='last_run'").fetchone()
    h["last_run"] = q[0] if q else None
    print(json.dumps(h, ensure_ascii=False, indent=1))

def cmd_search(a):
    con = _con()
    rows, total = search.search_articles(con, a.query, hours=a.hours, category=a.category,
                                         source=a.source, language=a.language,
                                         sort=a.sort, limit=a.limit, offset=a.offset)
    print(json.dumps({"total": total, "returned": len(rows), "results": rows}, ensure_ascii=False, indent=1))

def cmd_stories(a):
    con = _con()
    rows, total = search.search_stories(con, a.query, hours=a.hours, category=a.category,
                                        limit=a.limit, offset=a.offset)
    print(json.dumps({"total": total, "returned": len(rows), "results": rows}, ensure_ascii=False, indent=1))

def cmd_trending_view(a):
    from . import trending as trending_mod
    con = _con()
    print(json.dumps({"window_hours": a.window, "category": a.category,
                      "results": trending_mod.top(con, window_hours=a.window,
                                                  category=a.category, limit=a.limit)},
                     ensure_ascii=False, indent=1))

def cmd_latest(a):
    con = _con()
    rows, total = search.latest(con, hours=a.hours, category=a.category, limit=a.limit, offset=a.offset)
    print(json.dumps({"total": total, "returned": len(rows), "results": rows}, ensure_ascii=False, indent=1))

def cmd_story(a):
    con = _con(); print(json.dumps(search.get_story(con, a.id), ensure_ascii=False, indent=1))

def cmd_article(a):
    con = _con()
    d = search.get_article(con, a.id)
    if d and d.get("content") and a.summary:
        d["content"] = d["content"][:600] + "…"
    print(json.dumps(d, ensure_ascii=False, indent=1))

def cmd_sources(a):
    con = _con()
    print(json.dumps(search.list_sources(con), ensure_ascii=False, indent=1))

def cmd_doctor(a):
    con = _con()
    checks = {}
    checks["integrity"] = con.execute("PRAGMA quick_check").fetchone()[0]
    fts_n = con.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0]
    ex_n = con.execute("SELECT COUNT(*) FROM articles WHERE status='extracted' AND content IS NOT NULL").fetchone()[0]
    checks["fts_rows_vs_extracted"] = [fts_n, ex_n, "OK" if abs(fts_n - ex_n) <= 2 else "DRIFT"]
    checks["disabled_sources"] = [r["slug"] for r in con.execute(
        "SELECT slug FROM sources WHERE disabled=1").fetchall()]
    checks["stuck_tasks"] = con.execute(
        "SELECT COUNT(*) FROM crawl_tasks WHERE state='running' AND updated_at<?",
        (dbm.iso_ago(hours=1),)).fetchone()[0]
    checks["failures_24h"] = con.execute("SELECT COUNT(*) FROM crawl_errors WHERE at>=?",
                                         (dbm.iso_ago(hours=24),)).fetchone()[0]
    wal = pathlib.Path(str(config.DB_PATH) + "-wal")
    checks["wal_bytes"] = wal.stat().st_size if wal.exists() else 0
    checks["disk_level"] = __import__("news.images", fromlist=["monitor_level"]).monitor_level(con)
    print(json.dumps(checks, ensure_ascii=False, indent=1))

def cmd_backup(a):
    """SQLite backup API → ~/news-backups/ 保留最近 7 份"""
    con = _con()
    bdir = pathlib.Path.home() / "news-backups"; bdir.mkdir(exist_ok=True)
    dest = bdir / f"news-{time.strftime('%Y%m%d-%H%M')}.db"
    dst = sqlite3.connect(dest)
    with dst:
        con.backup(dst)
    dst.close(); con.close()
    gz = pathlib.Path(str(dest) + ".gz")
    gz.write_bytes(gzip.compress(dest.read_bytes(), 6))
    dest.unlink()
    backups = sorted(bdir.glob("news-*.db.gz"))
    for old in backups[:-7]:
        old.unlink()
    print(json.dumps({"backup": str(gz), "size": gz.stat().st_size, "kept": len(backups[:7])},
                     ensure_ascii=False))

def main(argv=None):
    p = argparse.ArgumentParser(prog="newsctl")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    sp = sub.add_parser("seed-sources"); sp.add_argument("--file", default=str(config.HOME / "sources.seed.json")); sp.set_defaults(fn=cmd_seed_sources)
    sp = sub.add_parser("scan"); sp.add_argument("--limit", type=int, default=None); sp.add_argument("--force", action="store_true"); sp.set_defaults(fn=cmd_scan)
    sp = sub.add_parser("fetch"); sp.add_argument("--limit", type=int, default=None); sp.set_defaults(fn=cmd_fetch)
    sp = sub.add_parser("images"); sp.add_argument("--limit", type=int, default=None); sp.set_defaults(fn=cmd_images)
    sp = sub.add_parser("cluster"); sp.add_argument("--window", type=int, default=72); sp.set_defaults(fn=cmd_cluster)
    sp = sub.add_parser("trending"); sp.add_argument("--window", type=int, default=24); sp.set_defaults(fn=cmd_trending)
    sp = sub.add_parser("cleanup"); sp.add_argument("--emergency", action="store_true"); sp.set_defaults(fn=cmd_cleanup)
    sp = sub.add_parser("run"); sp.add_argument("--scan-limit", type=int, default=None); sp.set_defaults(fn=cmd_run)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sp = sub.add_parser("search"); sp.add_argument("query"); sp.add_argument("--hours", type=int, default=None)
    sp.add_argument("--category", default=None); sp.add_argument("--source", default=None)
    sp.add_argument("--language", default=None); sp.add_argument("--sort", default="relevance", choices=["relevance", "recent"])
    sp.add_argument("--limit", type=int, default=20); sp.add_argument("--offset", type=int, default=0)
    sp.set_defaults(fn=cmd_search)
    sp = sub.add_parser("stories"); sp.add_argument("query"); sp.add_argument("--hours", type=int, default=None)
    sp.add_argument("--category", default=None); sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--offset", type=int, default=0); sp.set_defaults(fn=cmd_stories)
    sp = sub.add_parser("trending-top"); sp.add_argument("--window", type=int, default=24)
    sp.add_argument("--category", default=None); sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(fn=cmd_trending_view)
    sp = sub.add_parser("latest"); sp.add_argument("--hours", type=int, default=None)
    sp.add_argument("--category", default=None); sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--offset", type=int, default=0); sp.set_defaults(fn=cmd_latest)
    sp = sub.add_parser("story"); sp.add_argument("id", type=int); sp.set_defaults(fn=cmd_story)
    sp = sub.add_parser("article"); sp.add_argument("id", type=int); sp.add_argument("--summary", action="store_true"); sp.set_defaults(fn=cmd_article)
    sub.add_parser("sources").set_defaults(fn=cmd_sources)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sub.add_parser("backup").set_defaults(fn=cmd_backup)
    a = p.parse_args(argv)
    a.fn(a)

if __name__ == "__main__":
    main()
