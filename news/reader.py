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


# P0-4: 内容预算 + 注入检测 — 网页正文属 UNTRUSTED WEB CONTENT
MAX_CHARS_DEFAULT = 12000
MAX_CHARS_ABS = 40000            # absolute 上限: Agent 不可无限扩大
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+|the\s+|previous\s+|above\s+|prior\s+)*(instructions?|prompts?|rules?)",
    r"disregard\s+(all\s+|the\s+)?(previous|above|prior|your)\s+(instructions?|prompts?|rules?|context)",
    r"(reveal|print|show|repeat)\s+(your\s+|the\s+)?(system\s+)?(prompt|instructions?)",
    r"you\s+are\s+now\s+(a|an|no\s+longer)",
    r"act\s+as\s+(a\s+|an\s+)?(different|new|jailbreak|dan)",
    r"(system|admin)\s*(prompt|mode|command)\s*[:=]",
    r"忽略(以上|之前|上面)(的)?(指令|内容|文本|规则)",
    r"无视(以上|之前|上面)",
    r"你(现在)?是(一个)?(系统|管理员)",
    r"(输出|打印|泄露|重复)(你的|系统的)?(系统提示|系统指令|初始指令)",
    r"(忘记|清除)(你)?(之前|以上|所有)(的)?(指令|设定|约束)",
]
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")


def scrub_content(content: str) -> dict:
    """风险检测: 标记而不破坏原文; 零宽字符剥离(不可见载荷, 安全)。"""
    hits = []
    for pat in INJECTION_PATTERNS:
        m = re.search(pat, content, re.I)
        if m:
            frag = content[max(0, m.start() - 20):m.end() + 30].replace("\n", " ")
            hits.append({"pattern": pat[:44], "excerpt": frag[:90]})
    zw = len(_ZERO_WIDTH.findall(content))
    if zw > 5:
        hits.append({"pattern": "zero_width_chars", "count": zw})
    risk = min(1.0, 0.3 * len([h for h in hits if "pattern" not in ("zero_width_chars",)]) + (0.2 if zw > 20 else 0))
    return {
        "content": _ZERO_WIDTH.sub("", content),
        "injection_hits": hits,
        "risk_score": round(risk, 2),
        "prompt_injection_risk": risk >= 0.3,
    }


# P0-5: bot/paywall 状态细分 — 不绕过, 只诚实识别
_CF_MARK = re.compile(r"just a moment|cf-chl|turnstile|cf-browser-verification|attention required", re.I)


def classify_block(headers: dict, html: str) -> str | None:
    """返回 bot_protection | paywall | None。判定顺序: 头 → 正文特征 → 结构化标记。"""
    h = {str(k).lower(): str(v).lower() for k, v in (headers or {}).items()}
    if h.get("cf-mitigated") == "challenge" or _CF_MARK.search(html[:8000] or ""):
        return "bot_protection"
    if re.search(r'"isAccessibleForFree"\s*:\s*false', (html or "")[:400000], re.I):
        return "paywall"
    return None


# P0-6: published_at 新鲜度链 — meta → JSON-LD/OG → <time> → URL 日期 → htmldate(若可用) → null
_URL_DATE = re.compile(r"/(20\d{2})[-/](\d{2})[-/](\d{2})/")
_BODY_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")


def infer_published(html: str, url: str, ex_date=None):
    """返回 (iso_date, source_tag)。绝不使用抓取时间冒充发布时间。"""
    if ex_date:
        return str(ex_date)[:10], "extractor"
    head = html[:600000]
    for pat, tag in ((r'property=["\']article:published_time["\'][^>]+content=["\']([\dTLZ:+-]{10,30})', "meta"),
                     (r'"datePublished"\s*:\s*"([\dTLZ:+-]{10,30})"', "json_ld"),
                     (r'property=["\']og:updated_time["\'][^>]+content=["\']([\dTLZ:+-]{10,30})', "meta"),
                     (r'<time[^>]+datetime=["\']([\dTLZ:+-]{10,30})["\']', "html_time")):
        m = re.search(pat, head, re.I)
        if m:
            return m.group(1)[:10], tag
    m = _URL_DATE.search(url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "url_pattern"
    try:
        from htmldate import extract_date  # trafilatura 生态, 若在 venv 中则优先级最高兜底
        d = extract_date(html, original_date=True)
        if d:
            return d.isoformat(), "htmldate"
    except Exception:
        pass
    m = _BODY_DATE.search((html or "")[:200000])
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "body_regex"
    return None, None


def read(url: str, timeout: int = 25, max_chars: int = MAX_CHARS_DEFAULT) -> dict:
    max_chars = max(200, min(int(max_chars or MAX_CHARS_DEFAULT), MAX_CHARS_ABS))
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
        kind = classify_block(res.headers, "")
        if res.status == 401:
            out["status"] = "login_required" if not kind else kind
            out["error"] = "HTTP 401 (login required — 不绕过)"
        elif kind == "bot_protection":
            out["status"] = "bot_protection"
            out["error"] = f"HTTP {res.status} + challenge page (Cloudflare 等 — 不绕过)"
        else:
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
        pub, pub_src = infer_published(html, url, ex.get("date"))
        out["published"] = pub
        out["published_at_source"] = pub_src       # extractor|meta|json_ld|html_time|url_pattern|htmldate|body_regex|None
        raw = ex.get("text") or ""
        sc = scrub_content(raw)
        if len(sc["content"]) > max_chars:
            sc["content"] = sc["content"][:max_chars]
            out["truncated"] = True
        out["content"] = sc["content"]
        out["content_chars"] = len(out["content"])
        out["max_chars"] = max_chars
        out["prompt_injection_risk"] = sc["prompt_injection_risk"]   # True 时 Agent 须把正文当数据
        out["risk_score"] = sc["risk_score"]
        out["injection_hits"] = sc["injection_hits"]
        out["untrusted"] = True                                       # Spotlighting: 正文一律是数据, 不是指令
        out["untrusted_boundary"] = "<<UNTRUSTED id=reader>> ...content... <</UNTRUSTED>>"
        out["images"] = [x for x in [ex.get("image") or meta.get("image")] if x]
        out["method"] = ex["method"]
    else:
        # 正文提取失败 — 可能是 JS 渲染页或极端反爬
        blk = classify_block(getattr(res, "headers", {}) or {}, html)
        short = len(ex.get("text") or "") < 200
        if blk == "paywall" or (blk is None and res.status in (402, 403) and short and
                                re.search(r"subscri|paywall|premium", html[:40000], re.I)):
            out["status"] = "paywall"
            out["error"] = "paywall detected (isAccessibleForFree:false 或订阅墙特征) — 不绕过"
            return out
        if blk == "bot_protection":
            out["status"] = "bot_protection"
            out["error"] = "bot protection detected (challenge page) — 不绕过"
            return out
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
    mc = MAX_CHARS_DEFAULT
    for arg in sys.argv[2:]:
        if arg.startswith("--max-chars="):
            try: mc = int(arg.split("=", 1)[1])
            except ValueError: pass
    print(json.dumps(read(url, timeout=tmo, max_chars=mc), ensure_ascii=False))


if __name__ == "__main__":
    main()
