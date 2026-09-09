#!/usr/bin/env python3
"""check-sources.py — 来源审计报告（可再生）: 分布/评分/健康（degraded 只标不删）"""
import json, sqlite3, sys
from pathlib import Path
PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))
from news import db as dbm  # noqa: E402

def dist(con, col):
    return {r[0] or "-": r[1] for r in con.execute(f"SELECT {col}, COUNT(*) FROM sources GROUP BY {col} ORDER BY 2 DESC")}

def main():
    con = dbm.connect()
    dbm.migrate_ext if False else None
    from news.migrate_ext import ensure
    ensure(con)
    rep = {
        "generated_at": dbm.utcnow(),
        "totals": {"sources": con.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                   "active": con.execute("SELECT COUNT(*) FROM sources WHERE verification_status='active'").fetchone()[0],
                   "candidates": con.execute("SELECT COUNT(*) FROM candidate_sources").fetchone()[0]},
        "by_country": dist(con, "country"), "by_language": dist(con, "language"),
        "by_category": dist(con, "category"), "by_source_type": dist(con, "source_type"),
        "by_tier": dist(con, "tier"),
        "quality_avg": con.execute("SELECT ROUND(AVG(quality_score),1) FROM sources WHERE quality_score IS NOT NULL").fetchone()[0],
        "health": {"stale_24h": con.execute("SELECT COUNT(*) FROM sources WHERE disabled=0 AND last_scanned_at < datetime('now','-24 hours')").fetchone()[0] if any(r[1]=="last_scanned_at" for r in con.execute("PRAGMA table_info(sources)")) else "n/a",
                   "disabled": con.execute("SELECT COUNT(*) FROM sources WHERE disabled=1").fetchone()[0],
                   "errors_24h": con.execute("SELECT COUNT(*) FROM crawl_errors WHERE at >= datetime('now','-24 hours')").fetchone()[0]},
        "top_quality": [dict(r) for r in con.execute("SELECT slug, tier, quality_score FROM sources WHERE quality_score IS NOT NULL ORDER BY quality_score DESC LIMIT 10")],
    }
    # degraded 标记（不删除）: 长期未成功且禁用原因记录
    con.execute("""UPDATE sources SET disabled=1, disabled_reason=COALESCE(disabled_reason,'degraded:auto: long stale')
                   WHERE disabled=0 AND verification_status='active'
                   AND slug NOT IN (SELECT DISTINCT s.slug FROM sources s JOIN articles a ON a.source_id=s.id
                                    WHERE a.discovered_at >= datetime('now','-72 hours'))""")
    degraded = con.execute("SELECT COUNT(*) FROM sources WHERE disabled=1").fetchone()[0]
    rep["health"]["degraded_marked_total"] = degraded
    con.commit()
    p = Path(PROJ) / "news-data/state/source-audit.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps({k: rep[k] for k in ("totals", "by_tier", "by_source_type", "quality_avg")}, ensure_ascii=False, indent=1))
    print(f"审计已写: {p}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
