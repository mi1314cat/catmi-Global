#!/usr/bin/env python3
"""news.search — Phase 1 基础检索: FTS5 全文 + 条件过滤 + story/热点查询"""
import re
from datetime import datetime, timedelta

from . import db as dbm

_TOK = re.compile(r"[\w]{2,}", re.UNICODE)

def fts_query(q: str, mode="and") -> str | None:
    toks = _TOK.findall((q or "").lower())[:12]
    if not toks:
        return None
    quoted = [f'"{t}"' for t in toks]
    return (" OR " if mode == "or" else " ").join(quoted)

def _cutoff(hours):
    return dbm.iso_ago(hours=hours) if hours else None

def search_articles(con, q, *, hours=None, category=None, source=None, language=None,
                    sort="relevance", limit=20, offset=0):
    fts = fts_query(q)
    where, params = [], []
    if hours:
        where.append("((a.published_at IS NULL OR a.published_at>=?) OR (a.published_at IS NULL AND a.discovered_at>=?))")
        params += [_cutoff(hours), _cutoff(hours)]
    if category: where.append("a.category=?"); params.append(category)
    if language: where.append("a.language=?"); params.append(language)
    if source:
        where.append("s.slug=?"); params.append(source)
    wsql = (" WHERE " + " AND ".join(where)) if where else ""
    if fts:
        base = ("FROM articles_fts f JOIN articles a ON a.id=f.rowid JOIN sources s ON s.id=a.source_id "
                "WHERE articles_fts MATCH ?" + (" AND " + " AND ".join(where) if where else ""))
        bp = [fts] + params
        total = con.execute(f"SELECT COUNT(*) FROM (SELECT a.id {base})", bp).fetchone()[0]
        order = "ORDER BY bm25(articles_fts) ASC, a.discovered_at DESC" if sort == "relevance" \
            else "ORDER BY COALESCE(a.published_at, a.discovered_at) DESC"
        rows = con.execute(
            f"""SELECT a.id, a.title, a.original_title, a.url, a.canonical_url, a.author,
                a.published_at, a.discovered_at, a.language, a.category, a.story_id, a.status,
                a.extract_method, s.name AS source_name, s.slug AS source_slug,
                snippet(articles_fts, 1, '<mark>', '</mark>', '…', 12) AS snippet
                {base} {order} LIMIT ? OFFSET ?""", bp + [limit, offset]).fetchall()
        return [dict(r) for r in rows], total
    # 无 FTS 命中 → LIKE 兜底（title）
    like = f"%{(q or '').strip()}%"
    wsql = (" WHERE (a.title LIKE ? OR a.original_title LIKE ?)"
            + (" AND " + " AND ".join(where) if where else ""))
    lp = [like, like] + params
    total = con.execute(f"SELECT COUNT(*) FROM articles a JOIN sources s ON s.id=a.source_id {wsql}", lp).fetchone()[0]
    rows = con.execute(
        f"""SELECT a.id, a.title, a.original_title, a.url, a.author, a.published_at, a.discovered_at,
            a.language, a.category, a.story_id, a.status, s.name AS source_name, s.slug AS source_slug
            FROM articles a JOIN sources s ON s.id=a.source_id {wsql}
            ORDER BY COALESCE(a.published_at, a.discovered_at) DESC LIMIT ? OFFSET ?""",
        lp + [limit, offset]).fetchall()
    return [dict(r) for r in rows], total

def search_stories(con, q, *, hours=None, category=None, limit=20, offset=0):
    fts = fts_query(q, mode="or")
    where, params = ["st.status='active'"], []
    if fts:
        where.append("stories_fts MATCH ?"); params.append(fts)
    if hours: where.append("st.last_updated>=?"); params.append(_cutoff(hours))
    if category: where.append("st.category=?"); params.append(category)
    join = "JOIN stories_fts ON stories_fts.rowid=st.id" if fts else ""
    wsql = " AND ".join(where)
    total = con.execute(f"SELECT COUNT(*) FROM stories st {join} WHERE {wsql}", params).fetchone()[0]
    rows = con.execute(
        f"""SELECT st.*, bm25(stories_fts) AS rank FROM stories st {join} WHERE {wsql}
            ORDER BY {"bm25(stories_fts) ASC" if fts else "st.last_updated DESC"} LIMIT ? OFFSET ?""",
        params + [limit, offset]).fetchall() if fts else con.execute(
        f"""SELECT st.*, NULL AS rank FROM stories st WHERE {wsql}
            ORDER BY st.last_updated DESC LIMIT ? OFFSET ?""", params + [limit, offset]).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        a = con.execute("""SELECT a.id, a.title, a.url, a.published_at, a.image_main_url, s.name AS source_name,
                           s.slug AS source_slug FROM articles a JOIN sources s ON s.id=a.source_id
                           WHERE a.story_id=? ORDER BY COALESCE(a.published_at, a.discovered_at) DESC LIMIT 6""",
                        (d["id"],)).fetchall()
        d["articles"] = [dict(x) for x in a]
        out.append(d)
    return out, total

def latest(con, *, hours=None, category=None, limit=20, offset=0, include_purged=False):
    where, params = [], []
    if not include_purged: where.append("a.status!='purged'")
    if hours: where.append("COALESCE(a.published_at, a.discovered_at)>=?"); params.append(_cutoff(hours))
    if category: where.append("a.category=?"); params.append(category)
    wsql = (" WHERE " + " AND ".join(where)) if where else ""
    total = con.execute(f"SELECT COUNT(*) FROM articles a {wsql}", params).fetchone()[0]
    rows = con.execute(f"""SELECT a.id, a.title, a.url, a.author, a.published_at, a.discovered_at,
        a.language, a.category, a.story_id, a.status, a.image_main_url, s.name AS source_name, s.slug AS source_slug
        FROM articles a JOIN sources s ON s.id=a.source_id {wsql}
        ORDER BY COALESCE(a.published_at, a.discovered_at) DESC LIMIT ? OFFSET ?""",
        params + [limit, offset]).fetchall()
    return [dict(r) for r in rows], total

def trending(con, *, hours=24, category=None, limit=20):
    # [R3-P0-B] hours=活跃度窗口 (与 JS 对齐); trending 表只存 24 批次
    params = [(datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")]
    wcat = ""
    if category: wcat = " AND st.category=?"; params.append(category)
    rows = con.execute(f"""SELECT t.score, t.computed_at, st.id AS story_id, st.title, st.summary,
        st.first_seen, st.last_updated, st.importance, st.category, st.article_count, st.source_count,
        st.entities, st.locations
        FROM trending t JOIN stories st ON st.id=t.story_id
        WHERE t.window_hours=24 AND st.last_updated>=? {wcat}
        ORDER BY t.score DESC LIMIT ?""", params + [limit]).fetchall()
    return [dict(r) for r in rows]

def get_article(con, article_id):
    a = con.execute("""SELECT a.*, s.name AS source_name, s.slug AS source_slug, s.site_url
                       FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.id=?""",
                    (article_id,)).fetchone()
    if not a: return None
    d = dict(a)
    d.pop("raw_path", None)
    d["images"] = [dict(r) for r in con.execute(
        "SELECT id, original_url, local_path, content_hash, width, height, mime, main FROM images WHERE article_id=?",
        (article_id,))]
    if d.get("story_id"):
        st = con.execute("SELECT id,title,first_seen,last_updated,heat,importance,category,source_count "
                         "FROM stories WHERE id=?", (d["story_id"],)).fetchone()
        d["story"] = dict(st) if st else None
    return d

def get_story(con, story_id):
    st = con.execute("SELECT * FROM stories WHERE id=?", (story_id,)).fetchone()
    if not st: return None
    arts = con.execute("""SELECT a.id, a.title, a.url, a.author, a.published_at, a.discovered_at,
        a.category, a.language, a.image_main_url, a.status, s.name AS source_name, s.slug AS source_slug
        FROM story_articles sa JOIN articles a ON a.id=sa.article_id
        JOIN sources s ON s.id=a.source_id WHERE sa.story_id=?
        ORDER BY COALESCE(a.published_at, a.discovered_at) ASC""", (story_id,)).fetchall()
    d = dict(st)
    d["articles"] = [dict(r) for r in arts]
    d["timeline"] = [{"at": r["published_at"] or r["discovered_at"], "article_id": r["id"],
                      "title": r["title"], "source": r["source_name"], "url": r["url"]} for r in arts]
    return d

def list_sources(con, *, include_disabled=True):
    wsql = "" if include_disabled else " WHERE disabled=0"
    return [dict(r) for r in con.execute(f"SELECT * FROM sources{wsql} ORDER BY category, priority DESC, slug")]

def categories(con):
    return [dict(r) for r in con.execute(
        """SELECT COALESCE(category,'general') AS category, COUNT(*) AS n
           FROM articles GROUP BY category ORDER BY n DESC""")]
