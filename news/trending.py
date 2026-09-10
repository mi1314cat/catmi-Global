#!/usr/bin/env python3
"""news.trending — Phase 3: 热点排序（Heatwire heat 公式, 纯 SQL 可复现）
heat(story) = Σ_独立源 best(source.priority × exp(-age_h/30h))   仅统计窗口内
importance: heat>=6 major | >=3 high | >=1.2 normal | else low"""
import math
from datetime import datetime, timedelta, timezone

def _iso_ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

from . import config, db as dbm

HALF_LIFE_H = 30.0

def _age_hours(published_at, discovered_at, now_iso):
    t = dbm.parse_iso(published_at or discovered_at)
    n = dbm.parse_iso(now_iso)
    if not t or not n: return 999.0
    return max(0.0, (n - t).total_seconds() / 3600.0)

def run(con, window_hours=24):
    """重算窗口内活跃 story 的 heat + importance → trending 表"""
    now = dbm.utcnow()
    cutoff = dbm.iso_ago(hours=window_hours + 48)   # 聚类窗稍宽, 计算窗内过滤
    stories = con.execute("""SELECT id, first_seen FROM stories
                             WHERE status='active' AND last_updated>=?""", (cutoff,)).fetchall()
    n = 0
    for st in stories:
        arts = con.execute("""SELECT a.published_at, a.discovered_at, s.id AS sid, s.priority
                              FROM story_articles sa JOIN articles a ON a.id=sa.article_id
                              JOIN sources s ON s.id=a.source_id WHERE sa.story_id=?""", (st["id"],)).fetchall()
        per_source = {}
        for a in arts:
            age = _age_hours(a["published_at"], a["discovered_at"], now)
            if age > window_hours:
                continue
            w = a["priority"] * math.exp(-age / HALF_LIFE_H)
            per_source[a["sid"]] = max(per_source.get(a["sid"], 0.0), w)
        # 每源只取最佳权重（独立来源语义）
        heat = sum(per_source.values())
        importance = ("major" if heat >= 6 else "high" if heat >= 3 else
                      "normal" if heat >= 1.2 else "low")
        con.execute("""INSERT INTO trending(story_id, score, window_hours, computed_at) VALUES(?,?,?,?)
                       ON CONFLICT(story_id) DO UPDATE SET score=excluded.score,
                       window_hours=excluded.window_hours, computed_at=excluded.computed_at""",
                    (st["id"], round(heat, 3), window_hours, now))
        con.execute("UPDATE stories SET heat=?, importance=? WHERE id=?", (round(heat, 3), importance, st["id"]))
        n += 1
    con.commit()
    return {"recomputed": n, "window_hours": window_hours}


    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

def top(con, window_hours=24, category=None, limit=20):
    # [R3-P0-B] window_hours=活跃度窗口 (与 JS newsdb.trending 对齐); trending 表只存 24 批次
    params = [_iso_ago(window_hours)]
    wcat = ""
    if category:
        wcat = " AND st.category=?"; params.append(category)
    return [dict(r) for r in con.execute(f"""SELECT t.score, st.id AS story_id, st.title, st.importance,
               st.category, st.article_count, st.source_count, st.first_seen, st.last_updated, st.entities,
               st.locations FROM trending t JOIN stories st ON st.id=t.story_id
               WHERE t.window_hours=24 AND st.last_updated>=? {wcat} ORDER BY t.score DESC LIMIT ?""", params + [limit])]
