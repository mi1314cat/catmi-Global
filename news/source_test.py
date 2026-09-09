#!/usr/bin/env python3
"""news.source_test — 管理后台"测试来源": 单源实测一次（不写库）"""
import json
import sys

from . import db as dbm
from .collector import _HANDLERS
from .fetcher import Fetcher


def test_source(con, slug: str) -> dict:
    r = con.execute("SELECT * FROM sources WHERE slug=?", (slug,)).fetchone()
    if r is None:
        return {"ok": False, "error": f"unknown source: {slug}"}
    s = dict(r)  # row_factory=Row
    if s["kind"] not in _HANDLERS or _HANDLERS[s["kind"]] is None:
        return {"ok": False, "error": f"kind {s['kind']} has no handler"}
    f = Fetcher()
    try:
        res = f.get(s["feed_url"], etag=s["etag"], last_modified=s["last_modified"])
        if res.status == 304:
            return {"ok": True, "slug": slug, "status": 304, "note": "not modified (feed fresh)"}
        if res.status != 200:
            return {"ok": False, "slug": slug, "status": res.status, "error": res.error or f"HTTP {res.status}"}
        entries = _HANDLERS[s["kind"]](s, res, f)
        first = entries[0]["title"][:80] if entries else None
        return {"ok": True, "slug": slug, "status": 200, "entries": len(entries), "first": first,
                "latency_s": round(res.elapsed, 2) if hasattr(res, "elapsed") else None}
    except Exception as e:
        return {"ok": False, "slug": slug, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    finally:
        f.close()


def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else ""
    con = dbm.connect()
    try:
        print(json.dumps(test_source(con, slug), ensure_ascii=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()
