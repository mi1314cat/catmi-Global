#!/usr/bin/env python3
"""news.retention — 72h 滚动窗口 + 分层保留 + 磁盘保护联动（STORAGE_POLICY 的实现）
短期: 正文/图片/原始缓存 72h → 中期: 元数据 30d → 长期: story/时间线 90d
紧急模式: 只保元数据（立即清正文/图片/缓存），绝不损坏数据库核心。"""
import pathlib, sqlite3

from . import config, db as dbm
from .images import monitor_level

def purge_content(con, *, force_emergency=False):
    """正文超龄 → 置 NULL + status=purged + 删 FTS 行 + 删缓存文件。元数据保留。"""
    hours = 0 if force_emergency else config.RETENTION_CONTENT_H
    cutoff = dbm.iso_ago(hours=hours)
    rows = con.execute("""SELECT id, raw_path FROM articles WHERE content IS NOT NULL
                          AND COALESCE(published_at, discovered_at) < ?""", (cutoff,)).fetchall()
    n = 0
    for r in rows:
        if r["raw_path"]:
            try: pathlib.Path(r["raw_path"]).unlink(missing_ok=True)
            except Exception: pass
        con.execute("UPDATE articles SET content=NULL, raw_path=NULL, status='purged' WHERE id=?", (r["id"],))
        con.execute("DELETE FROM articles_fts WHERE rowid=?", (r["id"],))
        n += 1
    con.commit()
    return {"content_purged": n}

def purge_images(con, *, force_emergency=False):
    hours = 0 if force_emergency else config.RETENTION_IMAGES_H
    cutoff = dbm.iso_ago(hours=hours)
    rows = con.execute("""SELECT id, local_path FROM images WHERE purged_at IS NULL
                          AND downloaded_at < ?""", (cutoff,)).fetchall()
    n = 0
    for r in rows:
        if r["local_path"]:
            try: pathlib.Path(r["local_path"]).unlink(missing_ok=True)
            except Exception: pass
        con.execute("UPDATE images SET local_path=NULL, purged_at=? WHERE id=?", (dbm.utcnow(), r["id"]))
        n += 1
    con.commit()
    return {"images_purged": n}

def purge_raw_cache(con):
    """CACHE 目录整体按 24h 轮换（按文件 mtime）"""
    import time as _t
    cutoff = _t.time() - config.RETENTION_RAW_H * 3600
    n = 0
    for p in pathlib.Path(config.CACHE).rglob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink(); n += 1
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        except Exception:
            pass
    return {"raw_files_removed": n}

def archive_stories(con):
    """30d 无更新 story 归档（保留行, 供长期检索）; 90d 后可选删除——默认保留"""
    meta_cutoff = dbm.iso_ago(days=config.RETENTION_METADATA_D)
    r = con.execute("UPDATE stories SET status='archived' WHERE status='active' AND last_updated < ?",
                    (meta_cutoff,))
    con.commit()
    return {"stories_archived": r.rowcount}

def purge_tasks_errors(con):
    r1 = con.execute("DELETE FROM crawl_tasks WHERE state='done' AND updated_at < ?",
                     (dbm.iso_ago(days=7),))
    r2 = con.execute("DELETE FROM crawl_errors WHERE at < ?", (dbm.iso_ago(days=config.RETENTION_ERRORS_D),))
    con.commit()
    return {"tasks_removed": r1.rowcount, "errors_removed": r2.rowcount}

def _finalize(con):
    """清理后收尾: 记录 meta + WAL checkpoint 释放空间"""
    con.execute("INSERT INTO meta(key,value) VALUES('last_cleanup',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (dbm.utcnow(),))
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    con.commit()


def run(con, *, force_emergency=None):
    level = force_emergency or monitor_level(con)
    emergency = level == "emergency"
    out = {"disk_level": level}
    out.update(purge_raw_cache(con))
    out.update(purge_content(con, force_emergency=emergency))
    out.update(purge_images(con, force_emergency=emergency))
    out.update(archive_stories(con))
    out.update(purge_tasks_errors(con))
    _finalize(con)
    return out
