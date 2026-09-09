#!/usr/bin/env python3
"""news.images — Phase 2: 主图提取(og/twitter/JSON-LD/srcset 评分) + 下载 + 哈希去重 + 磁盘保护"""
import hashlib, json, pathlib, re

from . import config, db as dbm

_BAD = re.compile(r"logo|avatar|icon|sprite|banner|ads?[-_/]|pixel|1x1|tracking|favicon|placeholder|default", re.I)
_W = re.compile(r"[-_/](\d{2,4})x(\d{2,4})[-_.]")
_OG = [re.compile(p, re.I) for p in (
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
    r'<meta[^>]+name=["\']twitter:image[:\w]*["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image[:\w]*')]

def _meta_candidates(html):
    out = []
    for pat in _OG:
        m = pat.search(html[:400000])
        if m: out.append(m.group(1))
    for m in re.finditer(r'<script[^>]+ld\+json["\'][^>]*>(.*?)</script>', html[:400000], re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        stack = [d]
        while stack and len(out) < 4:
            x = stack.pop()
            if isinstance(x, dict):
                for k, v in x.items():
                    if k.lower() in ("image", "thumbnailurl") and isinstance(v, str):
                        out.append(v)
                    stack.append(v)
            elif isinstance(x, list):
                stack.extend(x)
    return out

def _img_candidates(html, limit=30):
    out = []
    for m in re.finditer(r"<img[^>]+>", html[:600000], re.I):
        tag = m.group(0)
        src = re.search(r'src=["\']([^"\']+)', tag, re.I)
        lazy = re.search(r'data-(?:src|lazy-src|original)=["\']([^"\']+)', tag, re.I)
        ss = re.search(r'srcset=["\']([^"\']+)', tag, re.I)
        w = re.search(r'width=["\']?(\d+)', tag)
        best = (lazy.group(1) if lazy else (src.group(1) if src else None))
        if ss and best:
            cand = [p.strip().split(" ")[0] for p in ss.group(1).split(",")]
            big = [c for c in cand if c and _W.search(c)]
            if big: best = big[-1]
        if best:
            out.append({"url": best, "w": int(w.group(1)) if w else 0,
                        "in_figure": bool(re.search(r"<figure", html[max(0, m.start()-200):m.start()], re.I))})
        if len(out) >= limit: break
    return out

def _score(c):
    s = 0.0; u = c["url"] or ""
    if _BAD.search(u): s -= 5
    if c.get("w"):
        s += min(c["w"], 1200) / 100.0
        if c["w"] < 300: s -= 3
    if c.get("in_figure"): s += 2
    if any(k in u.lower() for k in ("og", "large", "hero")): s += 1
    return s

def pick(html):
    cands = [{"url": u, "src": "meta", "w": 0} for u in _meta_candidates(html)]
    for c in _img_candidates(html):
        c["src"] = "img"; cands.append(c)
    seen, uniq = set(), []
    for c in cands:
        h = hashlib.sha256((c["url"] or "").encode()).hexdigest()[:12]
        if c["url"] and h not in seen:
            seen.add(h); uniq.append(c)
    uniq.sort(key=_score, reverse=True)
    return uniq

def download(fetcher, url) -> dict | None:
    if url.startswith("//"): url = "https:" + url
    if not url.startswith("http") or _BAD.search(url):
        return None
    h = fetcher.head(url)
    ct = (h.headers or {}).get("content-type", "")
    if h.status and h.status != 200: return None
    if ct and not ct.startswith("image"): return None
    size = int((h.headers or {}).get("content-length", "0") or 0)
    if size > config.IMAGE_MAX_BYTES: return None
    r = fetcher.client.get(url)   # 已知 image URL, 直接取
    if r.status_code != 200: return None
    data = r.content
    if len(data) < config.IMAGE_MIN_BYTES: return None
    return {"content": data, "content_hash": dbm.sha(data), "bytes": len(data),
            "mime": ct or r.headers.get("content-type", "image/jpeg")}

def save_file(content: bytes, content_hash: str) -> pathlib.Path:
    d = pathlib.Path(config.IMAGES) / dbm.utcnow()[:7]   # 2026-09 目录
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{content_hash[:16]}.jpg"
    p.write_bytes(content)
    return p

def run(con, fetcher, limit=None):
    """对已提取文章下载主图。磁盘 high/emergency 时自动降级。"""
    level = monitor_level(con)
    if level in ("high", "emergency"):
        return {"skipped": "disk_" + level, "done": 0}
    now = dbm.utcnow()
    rows = con.execute("""SELECT a.id, a.image_main_url, a.url AS article_url FROM articles a
        WHERE a.status='extracted' AND a.image_main_url IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM images i WHERE i.article_id=a.id AND i.main=1)
        ORDER BY a.id DESC LIMIT ?""", (limit or config.IMAGE_BATCH,)).fetchall()
    stats = {"done": 0, "dupe": 0, "fail": 0}
    for r in rows:
        try:
            res = download(fetcher, r["image_main_url"])
            if not res:
                # 失败: 插标记行(main=1, 不落盘)——保留 URL 元数据 + 停止每轮重试
                dbm.log_error(con, None, r["image_main_url"], "image", "image", "download failed (HEAD/size/precheck)")
                con.execute("""INSERT INTO images(article_id,original_url,local_path,content_hash,bytes,mime,main,downloaded_at,purged_at)
                               VALUES(?,?,NULL,NULL,0,NULL,1,?,?)""",
                            (r["id"], r["image_main_url"], now, now))
                stats["fail"] += 1; con.commit(); continue
            if con.execute("SELECT 1 FROM images WHERE content_hash=?", (res["content_hash"],)).fetchone():
                con.execute("""INSERT INTO images(article_id,original_url,local_path,content_hash,bytes,mime,main,downloaded_at,purged_at)
                               VALUES(?,?,NULL,?,0,?,1,?,?)""",
                            (r["id"], r["image_main_url"], res["content_hash"], res["mime"], now, now))
                stats["dupe"] += 1; con.commit(); continue
            p = save_file(res["content"], res["content_hash"])
            con.execute("""INSERT INTO images(article_id,original_url,local_path,content_hash,bytes,mime,main,downloaded_at)
                           VALUES(?,?,?,?,?,?,1,?)""",
                        (r["id"], r["image_main_url"], str(p), res["content_hash"], res["bytes"], res["mime"], now))
            stats["done"] += 1
        except Exception:
            try:
                con.execute("""INSERT INTO images(article_id,original_url,local_path,content_hash,bytes,mime,main,downloaded_at,purged_at)
                               VALUES(?,?,NULL,NULL,0,NULL,1,?,?)""",
                            (r["id"], r["image_main_url"], now, now))
            except Exception:
                pass
            stats["fail"] += 1
        con.commit()
    return stats

def monitor_level(con):
    """磁盘水位: 基于家目录 du 估算占配额百分比"""
    import subprocess
    try:
        out = subprocess.run(["du", "-sk", str(pathlib.Path.home())], capture_output=True, text=True, timeout=30)
        kb = int(out.stdout.split()[0])
    except Exception:
        return "normal"
    return config.disk_level(config.disk_usage_pct(kb * 1024))
