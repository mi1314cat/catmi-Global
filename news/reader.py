#!/usr/bin/env python3
"""news.reader — URL Reader（Agent 按需读取单页）

用法: venv/bin/python -m news.reader <URL> [--timeout 25]
输出: JSON {url,status,title,author,published,source,content,content_chars,images,language,canonical_url,method,error}

设计:
- 复用采集管道的 Fetcher（描述性 UA、重试、429 退避）与 extract_html 三级提取链
  （trafilatura → Scrapling 段落聚合 → 失败）
- 绝不绕过 CAPTCHA/登录/付费墙; 401/403/429 → status=inaccessible
- Crawl4AI 不默认启用（JS 动态页 → status=needs_js, 留给外部渲染 fallback）
- 无 DB 写入（纯读取, 不污染情报库; 情报库条目由 Collector 采集）
"""
import json
import re
import sys
import urllib.parse

from . import config
from .fetcher import Fetcher
from .extractor import extract_html, find_canonical



import ipaddress
import socket as _socket


def _assert_public_host(url: str):
    """防 SSRF: 只允许公网主机。localhost/私网 IPv4/IPv6/link-local/metadata 全拒绝。"""
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https"):
        raise ValueError("only http/https allowed")
    host = (p.hostname or "").lower()
    if not host:
        raise ValueError("no host")
    if host in ("localhost", "0.0.0.0") or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("blocked host")
    try:
        infos = _socket.getaddrinfo(host, None)
    except Exception as e:
        raise ValueError(f"dns fail: {e}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"blocked ip {ip}")
    return host


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _meta(html: str) -> dict:
    """og/twitter/JSON-LD 元数据（标题/图/作者/日期/语言）"""
    out = {}
    head = html[:400000]
    og = re.search(r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)', head, re.I) \
        or re.search(r'content=["\']([^"\']+)["\'][^>]+property=["\']og:image', head, re.I)
    if og:
        out["image"] = og.group(1)
    lang = re.search(r'<html[^>]+lang=["\']([a-zA-Z-]{2,10})["\']', head)
    if lang:
        out["language"] = lang.group(1)
    if "author" not in out:
        am = re.search(r'name=["\']author["\'][^>]+content=["\']([^"\']+)', head, re.I)
        if am:
            out["author"] = am.group(1)[:200]
    return out


def read(url: str, timeout: int = 25) -> dict:
    out = {"url": url, "status": "failed", "title": None, "author": None, "published": None,
           "source": _domain(url), "content": None, "content_chars": 0, "images": [],
           "language": None, "canonical_url": None, "method": None, "error": None}
    try:
        _assert_public_host(url)
    except ValueError as e:
        out["status"] = "inaccessible"
        out["error"] = f"SSRF guard: {e}"
        return out
    f = Fetcher()
    try:
        res = f.get(url, retries=2)  # Fetcher 自带超时/重试; 读页用 2 次重试控时长
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        return out
    finally:
        f.close()
    if res.status in (401, 403, 429):
        out["status"] = "inaccessible"
        out["error"] = f"HTTP {res.status} (access control / rate limit — 不绕过)"
        return out
    ctype = (getattr(res, "headers", {}) or {}).get("content-type", "")
    if ctype and not ctype.split(";")[0].strip().startswith(("text/html", "text/plain", "application/xhtml", "application/xml", "text/xml", "application/json")):
        out["status"] = "failed"
        out["error"] = f"unsupported content-type: {ctype[:60]}"
        return out
    if res.status != 200 or not res.text:
        out["error"] = f"HTTP {res.status}"
        return out
    html = res.text[:5_000_000]  # 最大响应 5MB
    ex = extract_html(html)
    meta = _meta(html)
    out["canonical_url"] = find_canonical(html, url)
    out["language"] = meta.get("language")
    if ex["method"] in ("trafilatura", "scrapling_fallback"):
        out["status"] = "ok"
        out["title"] = ex.get("title")
        out["author"] = ex.get("author") or meta.get("author")
        out["published"] = ex.get("date")
        out["content"] = ex.get("text")
        out["content_chars"] = len(out["content"] or "")
        out["images"] = [x for x in [ex.get("image") or meta.get("image")] if x]
        out["method"] = ex["method"]
    else:
        # 正文提取失败 — 可能是 JS 渲染页或极端反爬
        title_m = re.search(r"<title[^>]*>([^<]{4,300})</title>", html, re.I)
        if title_m and len(html) > 20000:
            out["status"] = "needs_js"        # 有完整 HTML 但无正文 → 动态渲染概率高
            out["title"] = re.sub(r"\s+", " ", title_m.group(1)).strip()
            out["error"] = "no extractable text (likely JS-rendered; Crawl4AI fallback off)"
        else:
            out["status"] = "failed"
            out["error"] = "no extractable content"
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    url = args[0] if args else ""
    tmo = 25
    for a in sys.argv[1:]:
        if a.startswith("--timeout"):
            try:
                tmo = int(a.split("=")[-1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
            except Exception:
                pass
    if not url.startswith(("http://", "https://")):
        print(json.dumps({"url": url, "status": "failed", "error": "仅支持 http/https URL（其他协议拒绝）"}))
        return
    print(json.dumps(read(url, timeout=tmo), ensure_ascii=False))


if __name__ == "__main__":
    main()
