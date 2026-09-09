#!/usr/bin/env python3
"""evidence-report.py — 事件证据统计: source_count vs independent_source_count vs fact_status"""
import json, sqlite3, sys
from pathlib import Path
PROJ = Path(__file__).resolve().parent.parent
DB = Path(PROJ) / "news-data/database/news.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); con.row_factory = sqlite3.Row
rows = con.execute("""SELECT s.id, s.title, s.fact_status, s.independent_source_count,
    (SELECT COUNT(*) FROM articles a WHERE a.story_id=s.id) AS article_count,
    (SELECT COUNT(DISTINCT e.domain) FROM event_evidence e WHERE e.story_id=s.id) AS domains
    FROM stories s WHERE s.status='active' AND s.independent_source_count IS NOT NULL
    ORDER BY s.last_updated DESC LIMIT 30""").fetchall()
out = {"stories": [dict(r) for r in rows],
       "compressed": sum(1 for r in rows if r["article_count"] > r["independent_source_count"]),
       "fact_status_dist": {}}
for r in con.execute("SELECT fact_status, COUNT(*) FROM stories WHERE fact_status IS NOT NULL GROUP BY 1"):
    out["fact_status_dist"][r[0]] = r[1]
p = Path(PROJ) / "news-data/state/evidence-report.json"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps({"fact_status_dist": out["fact_status_dist"], "compressed_stories": out["compressed"],
                  "sample": [dict(r) for r in rows[:5]]}, ensure_ascii=False, indent=1))
print(f"报告已写: {p}")
