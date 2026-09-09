#!/usr/bin/env python3
"""news.fetcher — HTTP 抓取层: 礼貌延迟/条件GET/退避重试/字节上限/磁盘保护钩子"""
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from . import db as dbm
from . import config


@dataclass
class Result:
    url: str
    status: int
    text: str = ""
    content: bytes = b""
    headers: dict = field(default_factory=dict)
    elapsed: float = 0.0
    error: str = ""


_RETRYABLE = {403, 404, 408, 429, 500, 502, 503, 504, 522, 524}  # 404: YouTube 等间歇故障实测需重试


class Fetcher:
    def __init__(self):
        self.client = httpx.Client(
            timeout=config.HTTP_TIMEOUT, follow_redirects=True,
            headers={"User-Agent": config.UA,
                     "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml,application/json;q=0.9,*/*;q=0.8",
                     "Accept-Language": "en"},
            http2=True)
        self._last_hit = {}          # host -> monotonic

    def close(self):
        self.client.close()

    # -- 礼貌延迟（同域最小间隔） --
    def _polite(self, url):
        host = urlsplit(url).netloc.lower()
        wait = config.DOMAIN_DELAY - (time.monotonic() - self._last_hit.get(host, 0))
        if wait > 0:
            time.sleep(min(wait, config.DOMAIN_DELAY))
        self._last_hit[host] = time.monotonic()

    def get(self, url, *, etag=None, last_modified=None, retries=None) -> Result:
        """带重试/退避/条件GET 的抓取。429 尊重 Retry-After。"""
        retries = retries if retries is not None else config.HTTP_RETRIES
        headers = {}
        if etag: headers["If-None-Match"] = etag
        if last_modified: headers["If-Modified-Since"] = last_modified
        t0 = time.time()
        last = Result(url=url, status=0, error="init")
        for i in range(retries):
            self._polite(url)
            try:
                r = self.client.get(url, headers=headers or None)
                hd = dict(r.headers)
                if r.status_code == 304:
                    return Result(url, 304, headers=hd, elapsed=time.time() - t0)
                if r.status_code == 429 and i < retries - 1:
                    ra = hd.get("retry-after")
                    delay = float(ra) if (ra or "").isdigit() else config.RETRY_DELAYS[min(i, 1)]
                    time.sleep(min(delay, 30))
                    continue
                if r.status_code in _RETRYABLE and i < retries - 1:
                    time.sleep(config.RETRY_DELAYS[min(i, 1)])
                    continue
                text = ""
                try:
                    text = r.text
                except Exception:
                    text = r.content.decode("utf-8", "replace")[:config.CONTENT_MAX_CHARS]
                return Result(url, r.status_code, text=text[:config.CONTENT_MAX_CHARS * 3],
                              content=r.content[: (1 << 22)], headers=hd, elapsed=time.time() - t0)
            except Exception as e:
                last = Result(url=url, status=0, error=f"{type(e).__name__}: {str(e)[:150]}",
                              elapsed=time.time() - t0)
                if i < retries - 1:
                    time.sleep(config.RETRY_DELAYS[min(i, 1)])
        return last

    def head(self, url) -> Result:
        self._polite(url)
        try:
            r = self.client.head(url)
            return Result(url, r.status_code, headers=dict(r.headers))
        except Exception as e:
            return Result(url, 0, error=f"{type(e).__name__}: {str(e)[:120]}")


def source_mark_ok(con, source_id, headers: dict):
    con.execute("""UPDATE sources SET last_fetch_at=?, last_ok_at=?, consecutive_failures=0,
                   etag=COALESCE(?, etag), last_modified=COALESCE(?, last_modified) WHERE id=?""",
                (dbm.utcnow(), dbm.utcnow(), headers.get("etag"), headers.get("last-modified"), source_id))

def source_mark_fail(con, source_id, url, stage, detail):
    con.execute("""UPDATE sources SET last_fetch_at=?, consecutive_failures=consecutive_failures+1,
                   disabled=CASE WHEN consecutive_failures+1>=? THEN 1 ELSE disabled END,
                   disabled_reason=CASE WHEN consecutive_failures+1>=? THEN ? ELSE disabled_reason END
                   WHERE id=?""",
                (dbm.utcnow(), config.SOURCE_DISABLE_AFTER, config.SOURCE_DISABLE_AFTER,
                 f"auto-disabled after {config.SOURCE_DISABLE_AFTER} failures", source_id))
    dbm.log_error(con, source_id, url, stage, "fetch", detail)
