#!/usr/bin/env python3
"""news.extractor — Phase 2: 正文抓取+提取(trafilatura→Scrapling兜底→RSS摘要) + canonical/去重 + 72h缓存"""
import gzip, hashlib, json, re, pathlib

from . import config, db as dbm

_CANON_PATTERNS = [re.compile(p, re.I) for p in (
    r"<link[^>]+rel=[\"']canonical[\"'][^>]+href=[\"']([^\"']+)",
    r"<meta[^>]+property=[\"']og:url[\"'][^>]+content=[\"']([^\"']+)")]

def find_canonical(html: str, fallback_url: str) -> str:
    for pat in _CANON_PATTERNS:
        m = pat.search(html[:300000])
        if m:
            from urllib.parse import urljoin
            return urljoin(fallback_url, m.group(1))
    return fallback_url

def _valid(text, title):
    return bool(text) and len(text) >= config.EXTRACT_MIN_CHARS and bool(title)

def extract_html(html: str, rss_title=None, rss_summary=None) -> dict:
    """返回 {method,title,author,date,text,image}; 全失败时 rss 摘要兜底"""
    import trafilatura
    raw = None
    try:
        raw = trafilatura.extract(html, output_format="json", with_metadata=True,
                                  include_images=True, include_comments=False, favor_recall=True)
    except Exception:
        raw = None
    if raw:
        try:
            d = json.loads(raw)
            author = d.get("author")
            if isinstance(author, list): author = ", ".join(x for x in author if x)
            text = (d.get("text") or "")[:config.CONTENT_MAX_CHARS]
            if _valid(text, d.get("title")):
                return {"method": "trafilatura", "title": (d.get("title") or "").strip(),
                        "author": author, "date": d.get("date"), "text": text,
                        "image": d.get("image")}
        except Exception:
            pass
    # 兜底1: Scrapling CSS 段落聚合
    try:
        from scrapling import Selector
        s = Selector(content=html)
        t = (s.css("title::text").get() or "").strip()
        paras = "\n".join(p.strip() for p in s.css("p::text").getall() if len(p.strip()) > 40)
        if _valid(paras, t):
            og = None
            m = re.search(r'og:image["\'][^>]+content=["\']([^"\']+)', html[:300000], re.I) or \
                re.search(r'content=["\']([^"\']+)["\'][^>]+og:image', html[:300000], re.I)
            if m: og = m.group(1)
            return {"method": "scrapling_fallback", "title": t, "author": None, "date": None,
                    "text": paras[:config.CONTENT_MAX_CHARS], "image": og}
    except Exception:
        pass
    # 兜底2: RSS 摘要（标记降级, 不算正文）
    if rss_summary:
        txt = re.sub(r"<[^>]+>", " ", rss_summary)
        txt = re.sub(r"\s+", " ", txt).strip()
        if len(txt) >= 40:
            return {"method": "rss_summary", "title": rss_title, "author": None, "date": None,
                    "text": txt[:4000], "image": None}
    return {"method": "failed", "title": None, "author": None, "date": None, "text": "", "image": None}

def _cache_raw(con, article_id, url, html) -> str | None:
    """72h 原始页面 gz 缓存（磁盘保护时跳过）"""
    try:
        d = pathlib.Path(config.CACHE) / dbm.utcnow()[:10]
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{article_id}.html.gz"
        p.write_bytes(gzip.compress(html.encode("utf-8", "replace")[:3_000_000], 6))
        return str(p)
    except Exception:
        return None

def run(con, fetcher, limit=None):
    """处理 pending article 任务: 抓取→提取→canonical/content_hash 去重→缓存。"""
    now = dbm.utcnow()
    tasks = con.execute("""
        SELECT t.id AS tid, t.attempts, a.id AS aid, a.url, a.original_title, a.title,
               a.source_id, s.slug AS source_slug, a.published_at
        FROM crawl_tasks t JOIN articles a ON a.id=t.article_id
        JOIN sources s ON s.id=a.source_id
        WHERE t.kind='article' AND t.state IN ('pending','failed')
          AND (t.next_attempt_at IS NULL OR t.next_attempt_at<=?)
          AND a.source_id NOT IN (SELECT COALESCE(source_id,-1) FROM crawl_errors
                                  WHERE at>=? GROUP BY source_id HAVING COUNT(*)>=?)   -- [R6-P0-S2] 来源熔断
        ORDER BY t.id LIMIT ?""", (now, dbm.iso_ago(hours=24), config.SOURCE_BREAKER_ERRORS, limit or config.FETCH_BATCH)).fetchall()
    stats = {"done": 0, "noextract": 0, "failed": 0, "dupe": 0}
    for t in tasks:
        con.execute("UPDATE crawl_tasks SET state='running', updated_at=? WHERE id=?", (now, t["tid"]))
        con.commit()
        try:
            res = fetcher.get(t["url"])
            if res.status != 200 or not res.text or len(res.text) < 500:
                raise RuntimeError(f"HTTP {res.status} len={len(res.text)} {res.error}")
            html = res.text
            summ = con.execute("SELECT summary_text FROM articles WHERE id=?", (t["aid"],)).fetchone()
            art = extract_html(html, t["original_title"], (summ or {})["summary_text"] if summ else None)
            if art["method"] == "failed":
                raise RuntimeError("extract failed all fallbacks")
            chash = dbm.sha(art["text"].encode())
            canonical = find_canonical(html, t["url"])
            # --- Article Dedup: content_hash 精确 / canonical 精确 ---
            dupe = con.execute("""SELECT id FROM articles WHERE id!=? AND status='extracted'
                                  AND (content_hash=? OR (canonical_url=? AND canonical_url!=''))
                                  ORDER BY id LIMIT 1""",
                                (t["aid"], chash, canonical)).fetchone()
            if dupe:
                con.execute("""UPDATE articles SET canonical_url=?, content_hash=?, status='dupe',
                               dupe_of=?, extract_method=?, error='duplicate content/canonical',
                               fetched_at=? WHERE id=?""",
                            (canonical, chash, dupe[0], art["method"], now, t["aid"]))
                con.execute("UPDATE crawl_tasks SET state='done', updated_at=? WHERE id=?", (now, t["tid"]))
                stats["dupe"] += 1; con.commit(); continue
            # RSS 时间兜底: 提取无日期时沿用源 published_at
            # 注: FTS5 虚拟表不支持 UPSERT → 先删后插（顺序保证无部分写入:
            #     fts 成功才更新 articles; fts 失败则任务重试, 文章保持原状）
            con.execute("DELETE FROM articles_fts WHERE rowid=?", (t["aid"],))
            if art["text"]:
                con.execute("INSERT INTO articles_fts(rowid,title,text) VALUES(?,?,?)",
                            (t["aid"], art["title"] or t["original_title"] or "", art["text"][:50000]))
            con.execute("""UPDATE articles SET canonical_url=?, title=?, author=?, published_at=?,
                           content=?, content_hash=?, status=?, extract_method=?, image_main_url=?,
                           fetched_at=?, language=COALESCE(NULLIF(language,''),?),
                           category=COALESCE(category, 'general'),
                           raw_path=COALESCE(?, raw_path) WHERE id=?""",
                        (canonical, art["title"] or t["original_title"], art["author"],
                         art["date"] or t["published_at"],
                         art["text"] or None, chash if art["text"] else None,
                         "extracted" if art["method"] != "rss_summary" else "noextract",
                         art["method"], art["image"], now, "en",
                         _cache_raw(con, t["aid"], t["url"], html) if art["method"] != "rss_summary" else None,
                         t["aid"]))
            con.execute("""UPDATE crawl_tasks SET state='done', attempts=attempts+1, updated_at=? WHERE id=?""",
                        (now, t["tid"]))
            stats["done" if art["method"] != "rss_summary" else "noextract"] += 1
        except Exception as ex:
            attempts = t["attempts"] + 1
            if attempts >= config.TASK_MAX_ATTEMPTS:
                con.execute("""UPDATE articles SET status='failed', error=? WHERE id=?""",
                            (str(ex)[:300], t["aid"]))
                con.execute("""UPDATE crawl_tasks SET state='failed', attempts=?, last_error=?,
                               updated_at=? WHERE id=?""", (attempts, str(ex)[:300], now, t["tid"]))
                dbm.log_error(con, t["source_id"], t["url"], "extract", "task_failed", str(ex)[:200])
                stats["failed"] += 1
            else:
                backoff = config.TASK_RETRY_BACKOFF[min(attempts - 1, len(config.TASK_RETRY_BACKOFF) - 1)]
                nxt = dbm.iso_ago(seconds=-backoff)
                con.execute("""UPDATE crawl_tasks SET state='failed', attempts=?, last_error=?,
                               next_attempt_at=?, updated_at=? WHERE id=?""",
                            (attempts, str(ex)[:300], nxt, now, t["tid"]))
                stats["failed"] += 0  # 可重试失败不计入最终失败
        con.commit()
    return stats
