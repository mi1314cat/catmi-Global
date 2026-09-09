#!/usr/bin/env python3
"""news.stories — v2: 事件聚类（专名锚点 + 标题词元双通道, ±72h 窗, 全确定性零 AI）
- 锚点(强信号): 专名/短语/缩略词 (e:) —— 跨源报道同一事件共享实体
- 词元(弱信号): 标题词元 Jaccard (t:/d:/w:) —— 同事件不同措辞的兜底
- 判定: anchor_containment≥0.5 或 title_jaccard≥0.30（先到先用, 记录 method/score）
可解释性: story_articles.method/score 记录每次归并依据。"""
import json, re

from . import config, db as dbm
from .collector import title_tokens, jaccard

_WORD = re.compile(r"[a-zA-Z]{2,}")
_STOP = set("the a an and or of to in on for with at by from as is are was were be been it its this that "
            "these those after before over under new says say said will would could news latest update "
            "updates report reports live amid one two three first".split())
# 首字母大写但非实体的噪声词（标题高频）
NOISE_CAPS = set("""update updates report reports watch video live analysis opinion breaking exclusive
monday tuesday wednesday thursday friday saturday sunday january february march april may june july
august september october november december q1 q2 q3 q4 ceo cfo ctos pms brief interview podcast
newsletter episode season part series photos photo picture pictures amid warned says said say will
would could should news ap reuters cnn bbc guardian npr cnbc dw nyt nytimes fox msnbc aljazeera
latest full read more top best worst key why how what who when where wsj ft""".split())
month_names = {"january", "february", "march", "april", "june", "july", "august", "september",
               "october", "november", "december"}
NOISE_CAPS |= month_names

_PHRASE = re.compile(r"\b([A-Z][\w&\.\-']+(?:[\s,]+(?:of|the|and|de|von|bin|al-)?[\s]*[A-Z][\w&\.\-']+){1,3})\b")
_ACRONYM = re.compile(r"\b[A-Z]{2,5}\b")
_CANONW = lambda w: w.lower().strip(".,:;!'\"()[]")

def proper_anchors(*texts) -> set:
    """从标题/摘要/正文头提取专名锚点（短语合并为 e:word_word，缩略词 e:us 等）"""
    anchors = set()
    text = " ".join(x for x in texts if x)
    if not text:
        return anchors
    for m in _PHRASE.finditer(text[:3000]):
        words = [_CANONW(w) for w in m.group(1).split()]
        words = [w for w in words if w]
        if len(words) >= 2 and not all(w in NOISE_CAPS for w in words):
            anchors.add("e:" + "_".join(words))
    for m in _ACRONYM.finditer(text[:2000]):
        w = m.group(0).lower()
        if w not in NOISE_CAPS:
            anchors.add("e:" + w)
    # 句中大写单词（非句首）—— 宽容提取, 由窗口+阈值过滤噪声
    for m in re.finditer(r"(?<![.!?…]\s)(?<!^)(?<!^ )\b([A-Z][a-z]{3,})\b", text[:2000]):
        w = _CANONW(m.group(1))
        if w not in NOISE_CAPS:
            anchors.add("e:" + w)
    return anchors

def body_tokens(text, cap=30):
    out, seen = [], set()
    for w in _WORD.findall((text or "").lower()):
        if len(w) >= 3 and w not in _STOP and w not in seen:
            seen.add(w); out.append(w)
        if len(out) >= cap:
            break
    return out

def fingerprint(title, domain, body_text, summary_text=None):
    anchors = proper_anchors(title, (summary_text or "")[:400], (body_text or "")[:1500])
    tokens = {f"t:{w}" for w in title_tokens(title)}
    if domain:
        tokens.add(f"d:{domain}")
    tokens |= {f"w:{w}" for w in body_tokens((body_text or summary_text or "")[:4000])}
    return anchors, tokens

def anchor_score(A: set, B: set) -> float:
    inter = len(A & B)
    if not inter:
        return 0.0
    return inter / min(len(A), len(B))     # containment: 对集合大小鲁棒

def _fts_story(con, story_id, title, anchors, tokens):
    """stories_fts: rowid=story id; 先删后插（FTS5 无 UPSERT）"""
    con.execute("DELETE FROM stories_fts WHERE rowid=?", (story_id,))
    con.execute("INSERT INTO stories_fts(rowid,title,entities,locations) VALUES(?,?,?,?)",
                (story_id, title[:300],
                 " ".join(x[2:] for x in sorted(anchors))[:2000],
                 " ".join(x[2:] for x in sorted(tokens) if x.startswith(("d:", "t:")))[:2000]))


def run(con, window_hours=None, threshold=None):
    """把窗口内未聚类文章归入 story（确定性; AI 可后续增强灰区）。"""
    window_hours = window_hours or 72
    threshold = threshold or 0.30
    now = dbm.utcnow()
    pending = con.execute("""SELECT a.id, a.title, a.original_title, a.published_at, a.discovered_at,
                             a.content, a.summary_text, s.category AS source_category, s.language,
                             s.slug AS source_slug
                             FROM articles a JOIN sources s ON s.id=a.source_id
                             WHERE a.story_id IS NULL AND a.status IN ('discovered','extracted','noextract','purged')
                               AND COALESCE(a.published_at, a.discovered_at) >= ?
                             ORDER BY COALESCE(a.published_at, a.discovered_at) ASC
                             LIMIT 300""", (dbm.iso_ago(hours=window_hours),)).fetchall()
    stats = {"joined": 0, "created": 0, "scanned": len(pending)}
    # 预载活跃 story: anchors/tokens/category/time
    stories = []
    for r in con.execute("""SELECT id, title, fingerprint, category, first_seen, last_updated FROM stories
                            WHERE status='active' AND last_updated >= ?""",
                          (dbm.iso_ago(hours=window_hours),)).fetchall():
        fpr = dbm.jload(r["fingerprint"], None)
        anchors, tokens = set(), set()
        if isinstance(fpr, dict):                       # v2 结构
            anchors = set(fpr.get("anchors", []))
            tokens = set(fpr.get("tokens", []))
        elif isinstance(fpr, list):                     # v1 平铺列表
            anchors = {x for x in fpr if x.startswith("e:")}
            tokens = {x for x in fpr if not x.startswith("e:")}
        stories.append({"id": r["id"], "title": r["title"], "category": r["category"],
                        "anchors": anchors, "tokens": tokens,
                        "last_seen": r["first_seen"] or r["last_updated"]})
    for a in pending:
        title = a["title"] or a["original_title"] or ""
        domain = (a["source_slug"] or "").replace("-", ".")
        anchors, tokens = fingerprint(title, domain, a["content"], a["summary_text"])
        if not anchors and not tokens:
            continue
        a_time = dbm.parse_iso(a["published_at"] or a["discovered_at"])
        best_score, best_method, best_story = 0.0, None, None
        for st in stories:
            acat = a["source_category"]
            if (st["category"] and acat
                    and st["category"] not in ("general", "video")
                    and acat not in ("general", "video")
                    and st["category"] != acat):
                continue
            sc = anchor_score(anchors, st["anchors"])
            # 最小交集 2: 单一泛锚点(us/eu/uk/ai...)不得单独触发归并
            inter = anchors & st["anchors"]
            if len(inter) < 2:
                sc = 0.0
            tj = jaccard(title_tokens(title), {t[2:] for t in st["tokens"] if t.startswith("t:")})
            if sc >= 0.5 and sc > best_score:
                best_score, best_method, best_story = sc, f"anchor:{sc:.2f}", st
            elif tj >= threshold and tj > best_score:
                best_score, best_method, best_story = tj, f"title:{tj:.2f}", st
        joined = best_story is not None
        if joined:
            # 时间窗: |article_time - story.last_updated| <= window
            st_time = dbm.parse_iso(best_story["last_seen"])
            if a_time and st_time and abs((a_time - st_time).total_seconds()) > window_hours * 3600:
                joined = False
        if joined:
            story_id = best_story["id"]
            stats["joined"] += 1
        else:
            scat = (a["source_category"]
                    if a["source_category"] not in ("general", "video") else None)
            cur = con.execute("""INSERT INTO stories(title, first_seen, last_updated, category, language,
                                  fingerprint) VALUES(?,?,?,?,?,?)""",
                              (title[:200], a["published_at"] or a["discovered_at"], now,
                               scat, a["language"],
                               json.dumps({"anchors": sorted(anchors), "tokens": sorted(tokens)})))
            story_id = cur.lastrowid
            _fts_story(con, story_id, title, anchors, tokens)
            stories.append({"id": story_id, "title": title[:200], "category": a["source_category"],
                            "anchors": anchors, "tokens": tokens, "last_seen": a["published_at"] or a["discovered_at"]})
            stats["created"] += 1
        con.execute("""INSERT INTO story_articles(story_id, article_id, method, score, joined_at)
                       VALUES(?,?,?,?,?) ON CONFLICT(article_id) DO UPDATE SET method=excluded.method""",
                    (story_id, a["id"], (best_method or "seed") if joined else "seed",
                     best_score if joined else 1.0, now))
        con.execute("UPDATE articles SET story_id=? WHERE id=?", (story_id, a["id"]))
        st_row = next(s for s in stories if s["id"] == story_id)
        if joined:
            st_row["anchors"] |= anchors
            st_row["tokens"] |= tokens
        if joined:
            _fts_story(con, story_id, st_row["title"], st_row["anchors"], st_row["tokens"])
        con.execute("""UPDATE stories SET fingerprint=?, last_updated=?,
                       article_count=(SELECT COUNT(*) FROM story_articles WHERE story_id=?),
                       source_count=(SELECT COUNT(DISTINCT a.source_id) FROM story_articles sa
                                     JOIN articles a ON a.id=sa.article_id WHERE sa.story_id=?),
                       video_count=(SELECT COUNT(*) FROM story_articles sa JOIN articles a ON a.id=sa.article_id
                                    JOIN sources s ON s.id=a.source_id WHERE sa.story_id=? AND s.category='video')
                       WHERE id=?""", (json.dumps({"anchors": sorted(st_row["anchors"]),
                                                   "tokens": sorted(st_row["tokens"])}),
                                       now, story_id, story_id, story_id, story_id))
        con.commit()
    return stats

def rebuild_counts(con):
    con.execute("""UPDATE stories SET
        article_count=(SELECT COUNT(*) FROM story_articles WHERE story_id=stories.id),
        source_count=(SELECT COUNT(DISTINCT a.source_id) FROM story_articles sa
                      JOIN articles a ON a.id=sa.article_id WHERE sa.story_id=stories.id)""")
    con.commit()
