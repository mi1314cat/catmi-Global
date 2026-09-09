"""news.evidence_model — Evidence 统一模型 (P0-1)

纯映射层: Article+Source → 统一 Evidence 结构。零新存储、零新表。
Evidence 追溯链: evidence.article_id → articles.source_id → sources → url/canonical_url
不复制 sources 质量表; published_at(发布) / fetched_at(抓取) / discovered_at(发现) 三时间分离。
score 字段由 P0-3(规则重排)/P0-6(freshness) 填充, 此处固定 None。
"""
import json
from . import config

EXCERPT_CHARS = 300


def _rowget(row, key, default=None):
    try:
        v = row[key]
        return default if v is None else v
    except (IndexError, KeyError, TypeError):
        return default


def to_evidence(a, s=None):
    """a: articles 行 (sqlite3.Row 或 dict); s: sources 行 (可选)。
    返回统一 Evidence dict — 同一字段名供 Python/MCP/Agent 共用。"""
    url = _rowget(a, "url") or ""
    canonical = _rowget(a, "canonical_url") or url
    content = _rowget(a, "content") or ""
    summary = _rowget(a, "summary_text") or ""
    return {
        "id": _rowget(a, "id"),
        "article_id": _rowget(a, "id"),
        "story_id": _rowget(a, "story_id"),
        "url": url,
        "canonical_url": canonical,
        "title": _rowget(a, "title") or _rowget(a, "original_title") or "",
        "author": _rowget(a, "author"),
        "source_id": _rowget(a, "source_id"),
        "source": _rowget(s, "name"),
        "source_type": _rowget(s, "source_type"),
        "tier": _rowget(s, "tier"),
        "quality_score": _rowget(s, "quality_score"),
        "verification_status": _rowget(s, "verification_status"),
        "published_at": _rowget(a, "published_at"),      # 发布时间 — 永远不用 fetched_at 冒充
        "published_at_source": "article.published_at" if _rowget(a, "published_at") else None,
        "retrieved_at": _rowget(a, "fetched_at"),        # 抓取时间
        "discovered_at": _rowget(a, "discovered_at"),    # 发现时间
        "language": _rowget(a, "language"),
        "content_chars": len(content) if content else 0,
        "excerpt": (summary[:EXCERPT_CHARS] if summary else content[:EXCERPT_CHARS]),
        "extract_method": _rowget(a, "extract_method"),  # trafilatura/scrapling_fallback/rss_summary
        "dupe_of": _rowget(a, "dupe_of"),
        # --- 评分字段 (P0-3/P0-6 填充) ---
        "relevance_score": None,
        "freshness_score": None,
        "source_quality_score": _rowget(s, "quality_score"),   # 直接复用 sources 表
        "final_score": None,
        "original_reporting": None,     # P0-3 由 event_evidence.is_original 补
        "independent_source": None,     # P0-3 由 event_evidence 补
    }


def load(con, article_id):
    """按 article_id 加载完整 Evidence (JOIN sources)"""
    row = con.execute("""SELECT a.*, s.name AS s_name, s.source_type AS s_type, s.tier AS s_tier,
                         s.quality_score AS s_quality, s.verification_status AS s_ver
                         FROM articles a LEFT JOIN sources s ON s.id = a.source_id
                         WHERE a.id = ?""", (article_id,)).fetchone()
    if not row:
        return None
    a = {"id": row["id"], "story_id": row["story_id"], "url": row["url"],
         "canonical_url": row["canonical_url"], "title": row["title"],
         "original_title": row["original_title"], "author": row["author"],
         "source_id": row["source_id"], "published_at": row["published_at"],
         "fetched_at": row["fetched_at"], "discovered_at": row["discovered_at"],
         "language": row["language"], "content": row["content"],
         "summary_text": row["summary_text"], "extract_method": row["extract_method"],
         "dupe_of": row["dupe_of"]}
    s = {"name": row["s_name"], "source_type": row["s_type"], "tier": row["s_tier"],
         "quality_score": row["s_quality"], "verification_status": row["s_ver"]} if row["s_name"] else None
    return to_evidence(a, s)
