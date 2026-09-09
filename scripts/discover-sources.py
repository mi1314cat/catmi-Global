#!/usr/bin/env python3
"""discover-sources.py — 来源发现流水线（规则实现, AI OFF 可用）
流程: 候选清单 → 抓取探测 → 内容分析 → 质量评分 → 重复检测 → candidate_sources 入库(默认 pending/rejected)
绝不直接写入 sources（生产采集表）。
用法: venv/bin/python scripts/discover-sources.py [--file news/candidates.seed.json] [--min-score 60]
"""
import json, re, sqlite3, sys, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from news import db as dbm, sourcesvc  # noqa: E402

PROJ = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def _norm_title(t):
    return re.sub(r"[^\w ]", "", (t or "").lower()).strip()

def probe(c):
    """抓取测试: 返回 probe dict"""
    p = {"http_status": 0, "items": 0, "titles": [], "ok": False}
    try:
        req = Request(c["feed_url"], headers={"User-Agent": UA})
        t0 = time.time()
        with urlopen(req, timeout=20) as r:
            body = r.read(1_500_000)
            p["http_status"] = r.status
        p["latency_ms"] = int((time.time() - t0) * 1000)
        text = body.decode("utf-8", "replace")
        root = ET.fromstring(re.sub(r"^.*?<\W*(rss|feed|urlset)", r"<\1", text, count=1, flags=re.S))
        items = root.iter()
        tags = [e.tag.rsplit("}", 1)[-1] for e in root.iter()]
        p["items"] = tags.count("item") + tags.count("entry")
        # 标题采样（重复检测用）
        for e in root.iter():
            if e.tag.rsplit("}", 1)[-1] in ("item", "entry"):
                for ch in e:
                    if ch.tag.rsplit("}", 1)[-1] == "title" and (ch.text or "").strip():
                        p["titles"].append(_norm_title(ch.text))
                        break
                if len(p["titles"]) >= 20:
                    break
        p["ok"] = p["http_status"] == 200 and p["items"] >= 5
    except (HTTPError, URLError, ET.ParseError, OSError) as e:
        p["error"] = str(e)[:200]
    return p

def dup_check(con, c, titles):
    """重复检测: 域名/标题相似度 vs 现有 sources"""
    dom = re.sub(r"^www\.", "", re.sub(r"^https?://", "", c["feed_url"]).split("/")[0])
    dup = {"domain_match": None, "title_overlap": 0.0}
    row = con.execute("SELECT slug FROM sources WHERE feed_url LIKE ?", (f"%{dom}%",)).fetchone()
    if row:
        dup["domain_match"] = row[0]
    rows = con.execute("SELECT url, title FROM articles ORDER BY id DESC LIMIT 3000").fetchall()
    ex_titles = {_norm_title(t) for _, t in rows if t}
    if titles and ex_titles:
        hit = sum(1 for t in titles if t in ex_titles)
        dup["title_overlap"] = round(hit / max(len(titles), 1), 2)
    return dup

def main():
    args = sys.argv[1:]
    f = Path(PROJ / "news/candidates.seed.json")
    if "--file" in args:
        f = Path(PROJ / args[args.index("--file") + 1])
    min_score = int(args[args.index("--min-score") + 1]) if "--min-score" in args else 60
    cands = json.loads(Path(f).read_text())
    con = dbm.connect()
    dbm.migrate_ext.ensure(con) if hasattr(dbm, "migrate_ext") else None
    try:
        from news import migrate_ext
        migrate_ext.ensure(con)
    except Exception as e:
        print(json.dumps({"error": f"migrate_ext 不可用: {e}"}))
        return 1
    out = {"probed": 0, "accepted": 0, "rejected": 0, "results": []}
    for c in cands:
        slug = c["slug"]
        if con.execute("SELECT 1 FROM sources WHERE slug=?", (slug,)).fetchone():
            out["results"].append({"slug": slug, "verdict": "already_active"})
            continue
        pr = probe(c)
        sc = sourcesvc.score_source(c)
        score, comps = sc["score"], sc["components"]
        dup = dup_check(con, c, pr.get("titles", []))
        reasons = []
        if not pr["ok"]:
            reasons.append(f"probe_failed(status={pr['http_status']},items={pr['items']})")
        if dup["domain_match"]:
            reasons.append(f"domain_dup:{dup['domain_match']}")
        if dup["title_overlap"] >= 0.7:
            reasons.append(f"title_overlap:{dup['title_overlap']}")
        if score < min_score:
            reasons.append(f"low_score:{score}")
        verdict = "rejected" if reasons else "review"
        # review = 人工审核候选（不自动启用）; probe 失败/重复/低分 = rejected
        status = verdict if verdict == "rejected" else "pending"
        con.execute("""INSERT INTO candidate_sources(slug,name,kind,feed_url,site_url,category,language,
                       country,source_type,tier,quality_score,verification_status,discovered_via,probe_json,notes,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(slug) DO UPDATE SET probe_json=excluded.probe_json,
                       quality_score=excluded.quality_score, verification_status=excluded.verification_status,
                       notes=excluded.notes, updated_at=excluded.updated_at""",
                    (slug, c["name"], c.get("kind", "rss"), c["feed_url"], c.get("site_url"),
                     c.get("category", "general"), c.get("language", "en"), c.get("country"),
                     c.get("source_type", "professional_media"), c.get("tier", "B"), score, status,
                     "manual-matrix", json.dumps({"probe": pr, "dup": dup, "score": comps}, ensure_ascii=False),
                     "; ".join(reasons), dbm.utcnow()))
        out["probed"] += 1
        out["accepted" if status == "pending" else "rejected"] += 1 if status == "pending" else 1
        out["results"].append({"slug": slug, "score": score, "items": pr["items"],
                               "dup_domain": dup["domain_match"], "overlap": dup["title_overlap"],
                               "verdict": status, "reasons": reasons})
    con.commit()
    (Path(PROJ) / "news-data/state/discovery-report.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for r in out["results"]:
        if r.get("verdict") != "already_active":
            print(f"{r['slug']:<24} score={r.get('score','-'):<4} items={r.get('items','-'):<4} → {r.get('verdict')} {'; '.join(r.get('reasons') or [])}")
    print(f"\nprobed={out['probed']} pending_review={out['accepted']} rejected={out['rejected']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
