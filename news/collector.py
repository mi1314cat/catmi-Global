#!/usr/bin/env python3
"""news.collector — v2: 多层数据源采集（handler 注册表）
kind: rss | gnews(feedparser) | sitemap(news sitemap, 支持 sitemapindex 链式) |
      api(JSON 适配器: hn_algolia / bilibili_popular) | gdelt(预留)
统一产出 entries: {url,title,summary,published,author,image,source_domain,meta_only}"""
import gzip
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import feedparser

from . import config, db as dbm
from .fetcher import Fetcher, source_mark_ok, source_mark_fail

_TRACK = re.compile(r"utm_\w+|fbclid|gclid|ref[_-]?(src|url)?|cmpid|ns_campaign|ns_mchannel|at_medium|at_campaign", re.I)
_WS = re.compile(r"\s+")
_GNEWS_SUFFIX = re.compile(r"\s+-\s+[^-]{2,40}$")

def normalize_url(url: str) -> str:
    p = urllib.parse.urlsplit(url.strip())
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not _TRACK.match(k or "")]
    out = urllib.parse.urlunsplit((p.scheme.lower() or "https", p.netloc.lower(), p.path or "/",
                                   urllib.parse.urlencode(q), ""))
    return _unwrap_bing(out)

def _unwrap_bing(url: str) -> str:
    """Bing News RSS 链接是 bing.com/news/...?...url=<原文> — 解包出真实 URL"""
    if "//www.bing.com/" not in url and "//bing.com/" not in url:
        return url
    try:
        p = urllib.parse.urlsplit(url)
        for k, v in urllib.parse.parse_qsl(p.query):
            if k == "url" and v.startswith("http"):
                return normalize_url(v)
    except Exception:
        pass
    return url

def title_tokens(t: str):
    return {w for w in re.findall(r"[a-z]{3,}", (t or "").lower()) if w not in
            set("the a an and or of to in on for with at by from as is are was were be been it its this that "
                "these those after before over under new says say said will would could news latest update "
                "updates report reports live amid".split())}

def jaccard(a, b):
    i = len(a & b)
    return i / len(a | b) if i else 0.0

def _ts_to_iso(ts):
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

# ---------------- handlers ----------------

def _handle_feed(s, res, fetcher):
    d = feedparser.parse(res.text)
    if d.bozo and not d.entries:
        raise RuntimeError(f"parse: {getattr(d, 'bozo_exception', 'bozo')}")
    out = []
    for e in d.entries[:config.MAX_ITEMS_PER_FEED]:
        link = e.get("link") or ""
        if not link.startswith("http"):
            continue
        title = _WS.sub(" ", (e.get("title") or "").strip())
        sdom = None
        if s["kind"] == "gnews":                       # 去尾 "- Source"; 取发布者域名
            src = e.get("source")
            if src and src.get("url"):
                sdom = urllib.parse.urlsplit(src["url"]).netloc.lower()
            title = _GNEWS_SUFFIX.sub("", title)
        img = None
        th = e.get("media_thumbnail") or []
        if th: img = th[0].get("url")
        summ = _WS.sub(" ", re.sub(r"<[^>]+>", " ", e.get("summary") or "")).strip()
        extra = ""
        try:                                           # YouTube 热度指标
            stat = e.get("media_statistics") or {}
            if stat.get("views"): extra = f"[views={stat['views']}]"
        except Exception:
            pass
        out.append({"url": normalize_url(link), "title": title, "summary": (extra + " " + summ)[:2000],
                    "published": entry_published(e), "author": e.get("author"),
                    "image": img, "source_domain": sdom})
    return out

def entry_published(e):
    for k in ("published_parsed", "updated_parsed"):
        st = e.get(k)
        if st:
            try:
                return datetime.fromtimestamp(__import__("time").mktime(st), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
    return None

def _handle_sitemap(s, res, fetcher):
    raw = res.content or res.text.encode("utf-8", "replace")
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    root = ET.fromstring(raw[:4_000_000])
    tag = lambda el: el.tag.split("}")[-1].lower()
    entries = []
    if tag(root) == "sitemapindex":                    # 链式: 抓最多 3 个子 sitemap
        subs = [el.text.strip() for el in root.iter() if tag(el) == "loc"][:3]
        for u in subs:
            r2 = fetcher.get(u)
            if r2.status == 200:
                entries.extend(_handle_sitemap({**s, "feed_url": u}, r2, fetcher))
                if len(entries) >= config.MAX_ITEMS_PER_FEED:
                    break
        return entries[:config.MAX_ITEMS_PER_FEED]
    for url_el in root.iter():                         # urlset (news sitemap)
        if tag(url_el) != "url":
            continue
        loc = title = pub = None
        for child in url_el.iter():
            t = tag(child)
            if t == "loc" and loc is None:
                loc = (child.text or "").strip()
            elif t == "title":
                title = (child.text or "").strip()
            elif t in ("publication_date", "lastmod"):
                pub = (child.text or "").strip()
        if loc and loc.startswith("http"):
            if pub:
                try:
                    pub = datetime.fromisoformat(pub.replace("Z", "+00:00")).strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    pub = None
            entries.append({"url": normalize_url(loc), "title": title or "", "summary": "",
                            "published": pub, "author": None, "image": None, "source_domain": None})
        if len(entries) >= config.MAX_ITEMS_PER_FEED:
            break
    return entries

def _hn_algolia(data):
    out = []
    for hit in (data.get("hits") or [])[:config.MAX_ITEMS_PER_FEED]:
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        title = hit.get("title") or hit.get("story_title") or ""
        if not title:
            continue
        out.append({"url": normalize_url(url), "title": title,
                    "summary": (hit.get("story_text") or hit.get("comment_text") or "")[:1500],
                    "published": _ts_to_iso(_iso_to_ts(hit.get("created_at"))),
                    "author": hit.get("author"), "image": None, "source_domain": None})
    return out

def _iso_to_ts(iso):
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except Exception:
        return None

def _bilibili_popular(data):
    out = []
    for v in ((data.get("data") or {}).get("list") or [])[:config.MAX_ITEMS_PER_FEED]:
        out.append({"url": normalize_url(f"https://www.bilibili.com/video/{v.get('bvid','')}"),
                    "title": (v.get("title") or "").strip(),
                    "summary": (v.get("desc") or "")[:200],
                    "published": _ts_to_iso(v.get("pubdate")),
                    "author": (v.get("owner") or {}).get("name"),
                    "image": v.get("pic"), "source_domain": "bilibili.com"})
    return out

_ADAPTERS = {"hn_algolia": _hn_algolia, "bilibili_popular": _bilibili_popular}

def _handle_api(s, res, fetcher):
    import json as _json
    data = _json.loads(res.text)
    adapter = s["adapter"] or (s["slug"].split("-")[0] if "-" in s["slug"] else s["slug"])
    fn = _ADAPTERS.get(adapter) or _ADAPTERS.get(s["slug"].split("-", 1)[-1].replace("-", "_"))
    if not fn:
        raise RuntimeError(f"no api adapter for {s['slug']}")
    return fn(data)

_HANDLERS = {"rss": _handle_feed, "gnews": _handle_feed, "sitemap": _handle_sitemap,
             "api": _handle_api, "gdelt": None}

# ---------------- 主流程 ----------------

def scan(con, fetcher: Fetcher, limit=None, force=False):
    from datetime import datetime as _dt, timedelta as _td
    rows = con.execute("""SELECT *, (CASE WHEN last_fetch_at IS NULL THEN 1e9
                          ELSE (strftime('%s','now') - strftime('%s', last_fetch_at)) * 1.0 / MAX(poll_seconds, 1) END)
                          AS overdue_ratio FROM sources WHERE disabled=0
                          ORDER BY overdue_ratio DESC, priority DESC""").fetchall()
    due = []
    for r in rows:
        if r["kind"] not in _HANDLERS or _HANDLERS[r["kind"]] is None:
            continue
        if force:
            due.append(r); continue
        d = dbm.parse_iso(r["last_fetch_at"])
        if d is None or (_dt.now(timezone.utc) - d) >= _td(seconds=r["poll_seconds"]):
            due.append(r)
    due = due[: (limit or config.SCAN_BATCH)]
    stats = {"sources": 0, "new": 0, "dup": 0, "errors": 0, "disabled_now": []}
    for s in due:
        stats["sources"] += 1
        try:
            res = fetcher.get(s["feed_url"], etag=s["etag"], last_modified=s["last_modified"])
            if res.status == 304:
                source_mark_ok(con, s["id"], res.headers); con.commit(); continue
            if res.status != 200:
                raise RuntimeError(f"HTTP {res.status} {res.error}")
            entries = _HANDLERS[s["kind"]](s, res, fetcher)
            new = dup = 0
            for e in entries:
                if not e["url"].startswith("http"):
                    continue
                if con.execute("SELECT 1 FROM articles WHERE url=?", (e["url"],)).fetchone():
                    dup += 1; continue
                title = _WS.sub(" ", (e["title"] or "").strip())
                tt = title_tokens(title)
                if tt:
                    hit = False
                    for (et,) in con.execute("SELECT title FROM articles WHERE source_id=? AND discovered_at>?",
                                             (s["id"], dbm.iso_ago(hours=48))):
                        if jaccard(tt, title_tokens(et)) >= 0.9:
                            dup += 1; hit = True; break
                    if hit:
                        continue
                _insert(con, s, e, title)
                new += 1
            source_mark_ok(con, s["id"], res.headers)
            con.execute("UPDATE sources SET items_total=items_total+? WHERE id=?", (new, s["id"]))
            stats["new"] += new; stats["dup"] += dup
        except Exception as ex:
            stats["errors"] += 1
            source_mark_fail(con, s["id"], s["feed_url"], "scan", str(ex)[:300])
            if con.execute("SELECT consecutive_failures FROM sources WHERE id=?", (s["id"],)).fetchone()[0] \
                    >= config.SOURCE_DISABLE_AFTER:
                stats["disabled_now"].append(s["slug"])
        con.commit()
    return stats

_CAT_HINTS = {
    "finance": ("stock", "market", "economy", "inflation", "bank", "fed ", "ecb", "gdp", "tariff",
                "oil", "gold", "crypto", "bitcoin", "earnings", "ipo", "trade", "dollar", "euro"),
    "tech": ("ai ", "artificial intelligence", "chip", "software", "startup", "openai", "google",
             "apple", "microsoft", "nvidia", "cyber", "hack", "data breach", "app", "quantum",
             "semiconductor", "tesla", "spacex", "github", "linux"),
    "geopolitics": ("war", "sanction", "military", "election", "summit", "treaty", "nato", "un ",
                    "diplomat", "border", "ceasefire", "missile", "protest", "coup"),
    "society": ("earthquake", "flood", "hurricane", "wildfire", "storm", "outbreak", "virus",
                "crash", "attack", "shooting", "killed", "dies", "police", "court"),
}

def _guess_category(title, lang):
    tl = (title or "").lower()
    for cat, hints in _CAT_HINTS.items():
        if any(h in tl for h in hints):
            return cat
    return "general"

def _insert(con, s, e, title):
    now = dbm.utcnow()
    video_meta = s["category"] == "video" or s["kind"] == "api"
    con.execute("""INSERT INTO articles(source_id,url,original_title,title,summary_text,published_at,
                   discovered_at,language,category,status,image_main_url,extract_method)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s["id"], e["url"], title, title, e.get("summary") or None, e.get("published"),
                 now, s["language"], s["category"] if s["category"] != "general"
                 else _guess_category(title, s["language"]),
                 "extracted" if video_meta else "discovered",
                 e.get("image"),
                 "meta_only" if video_meta else None))
    if not video_meta:
        aid = con.execute("SELECT id FROM articles WHERE url=?", (e["url"],)).fetchone()[0]
        con.execute("INSERT INTO crawl_tasks(article_id,url,kind,state,created_at,updated_at) "
                    "VALUES(?,?, 'article', 'pending', ?, ?)", (aid, e["url"], now, now))
