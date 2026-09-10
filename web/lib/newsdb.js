// lib/newsdb.js — 只读访问 news.db（与 Python 管道共享, WAL 多读单写）
// 零秘密: 本模块不含任何凭证; 只执行 SELECT。
'use strict';

const { toEvidence } = require('./evidence');
const { DatabaseSync } = require('node:sqlite');
const path = require('path');
const os = require('os');

const DB_PATH = process.env.NEWS_DB_PATH
  || path.join(os.homedir(), 'news-project', 'news-data', 'database', 'news.db');

let _db = null;
function db() {
  if (!_db) {
    try {
      _db = new DatabaseSync(DB_PATH, { readOnly: true });
    } catch (e) {
      _db = new DatabaseSync(DB_PATH); // 老版本无 readOnly 选项时降级
    }
    _db.exec('PRAGMA busy_timeout=5000');
  }
  return _db;
}

const STOP = new Set(('the a an and or of to in on for with at by from as is are was were be been it its ' +
  'this that these those after before over under new says say said will would could news latest update ' +
  'updates report reports live amid one two three first').split(' '));

function ftsQuery(q, mode) {
  const toks = (String(q || '').toLowerCase().match(/[\w]{2,}/g) || []).slice(0, 12);
  if (!toks.length) return null;
  const quoted = toks.map((t) => `"${t}"`);
  return (mode === 'or' ? quoted.join(' OR ') : quoted.join(' '));
}

// P1-2: CJK 术语提取 (FTS5 unicode61 把中文长串作整 token, 子串不命中)
function cjkTerms(q) { return (String(q || '').match(/[\u4e00-\u9fff]{2,}/g) || []).slice(0, 4); }

// 命中窗口 snippet: 找词在摘要/正文中的位置, 取窗口 (≤500 字符), 标 UNTRUSTED 由 toSearchEvidence 处理
function hitSnippet(text, terms) {
  const t = String(text || '');
  if (!t) return '';
  for (const term of terms) {
    const i = t.indexOf(term);
    if (i >= 0) {
      const s = Math.max(0, i - 100);
      return (s > 0 ? '…' : '') + t.slice(s, s + 500).replace(/<[^>]+>/g, '') + (s + 500 < t.length ? '…' : '');
    }
  }
  return t.slice(0, 200);
}

function isoAgo(hours) {
  return new Date(Date.now() - hours * 3600e3).toISOString().replace(/\.\d+Z$/, 'Z');
}

function rowObj(r) { return r; } // node:sqlite returns objects

// ---------- articles ----------
function searchArticles({ q, hours, category, source, language, sort, limit, offset, like: likeParam }) {
  limit = Math.max(1, Math.min(+limit || 20, 50)); offset = Math.max(+offset || 0, 0);
  const where = []; const params = [];
  if (hours) { where.push("COALESCE(a.published_at, a.discovered_at) >= ?"); params.push(isoAgo(+hours)); }
  if (category) { where.push('a.category = ?'); params.push(category); }
  if (language) { where.push('a.language = ?'); params.push(language); }
  if (source) { where.push('s.slug = ?'); params.push(source); }
  const wsql = where.length ? ' AND ' + where.join(' AND ') : '';
  const fts = ftsQuery(q);
  let rows, total;
  if (fts && String(q).trim()) {
    total = db().prepare(
      `SELECT COUNT(*) AS n FROM articles_fts f JOIN articles a ON a.id = f.rowid
       JOIN sources s ON s.id = a.source_id WHERE articles_fts MATCH ?${wsql}`
    ).get(fts, ...params).n;
    const order = sort === 'recent'
      ? 'ORDER BY COALESCE(a.published_at, a.discovered_at) DESC'
      : 'ORDER BY bm25(articles_fts), a.discovered_at DESC';
    rows = db().prepare(
      `SELECT a.id, a.story_id, a.title, a.original_title, a.url, a.canonical_url, a.author, a.source_id,
              a.published_at, a.fetched_at, a.discovered_at, a.language,
              substr(COALESCE(a.summary_text, a.content), 1, 500) AS excerpt,
              a.extract_method, a.category, a.status, a.image_main_url,
              s.id AS s_id, s.name, s.slug AS source_slug, s.source_type, s.tier, s.quality_score, s.verification_status,
              snippet(articles_fts, 1, '[', ']', '…', 12) AS snippet
       FROM articles_fts f JOIN articles a ON a.id = f.rowid JOIN sources s ON s.id = a.source_id
       WHERE articles_fts MATCH ?${wsql} ${order} LIMIT ? OFFSET ?`
    ).all(fts, ...params, limit, offset);
    if (!rows.length) { // P1-2: AND 0 命中 → OR 重试 → 仍无才 LIKE 兜底
      total = db().prepare(
        `SELECT COUNT(*) AS n FROM articles_fts f JOIN articles a ON a.id = f.rowid
         JOIN sources s ON s.id = a.source_id WHERE articles_fts MATCH ?${wsql}`).get(ftsQuery(q, 'or'), ...params).n;
      rows = db().prepare(
        `SELECT a.id, a.story_id, a.title, a.original_title, a.url, a.canonical_url, a.author, a.source_id,
              a.published_at, a.fetched_at, a.discovered_at, a.language,
              substr(COALESCE(a.summary_text, a.content), 1, 500) AS excerpt,
              a.extract_method, a.category, a.status, a.image_main_url,
              s.id AS s_id, s.name, s.slug AS source_slug, s.source_type, s.tier, s.quality_score, s.verification_status,
              snippet(articles_fts, 1, '[', ']', '…', 12) AS snippet
         FROM articles_fts f JOIN articles a ON a.id = f.rowid JOIN sources s ON s.id = a.source_id
         WHERE articles_fts MATCH ?${wsql} ORDER BY bm25(articles_fts), a.discovered_at DESC LIMIT ? OFFSET ?`
      ).all(ftsQuery(q, 'or'), ...params, limit, offset);
      if (!rows.length) return searchArticles({ q: null, hours, category, source, language, sort, limit, offset, like: q });
    }
  } else {
    const like = likeParam && String(likeParam).trim() ? `%${String(likeParam).trim()}%`
               : (q && String(q).trim() ? `%${String(q).trim()}%` : null);
    // P1-2: CJK 修复 — 每个中文词组独立 OR 匹配 (title+摘要), 不再要求整串子串
    const terms = like ? [like, ...cjkTerms(like).map((t) => `%${t}%`)] : null;
    const termSql = '(a.title LIKE ? OR a.original_title LIKE ? OR a.summary_text LIKE ?)';
    const likePart = terms ? `(${terms.map(() => termSql).join(' OR ')})` : null;
    const w2 = likePart ? (where.length ? ` WHERE ${where.join(' AND ')} AND ${likePart}` : ` WHERE ${likePart}`)
                    : (where.length ? ' WHERE ' + where.join(' AND ') : '');
    const lp = terms ? terms.flatMap((t) => [t, t, t]).concat(params) : params;
    const wfull = w2;
    total = db().prepare(
      `SELECT COUNT(*) AS n FROM articles a JOIN sources s ON s.id = a.source_id${wfull}`
    ).get(...lp).n;
    rows = db().prepare(
      `SELECT a.id, a.story_id, a.title, a.original_title, a.url, a.canonical_url, a.author, a.source_id,
              a.published_at, a.fetched_at, a.discovered_at, a.language, a.summary_text, a.extract_method,
              a.category, a.status, a.image_main_url,
              s.id AS s_id, s.name, s.slug AS source_slug, s.source_type, s.tier, s.quality_score, s.verification_status
       FROM articles a JOIN sources s ON s.id = a.source_id${wfull}
       ORDER BY COALESCE(a.published_at, a.discovered_at) DESC LIMIT ? OFFSET ?`
    ).all(...lp, limit, offset);
    const cterms = like ? cjkTerms(like) : [];
    for (const r of rows) r.snippet = hitSnippet(r.summary_text, cterms.length ? cterms : [String(like || '').replace(/%/g, '')]);
  }
  return { total, limit, offset, results: rows };
}

function latestArticles({ hours, category, limit, offset, includePurged }) {
  limit = Math.max(1, Math.min(+limit || 20, 50)); offset = Math.max(+offset || 0, 0);
  const where = [];
  if (!includePurged) where.push("a.status != 'purged'");
  if (hours) { where.push('COALESCE(a.published_at, a.discovered_at) >= ?'); }
  if (category) { where.push('a.category = ?'); }
  const params = [];
  if (hours) params.push(isoAgo(+hours));
  if (category) params.push(category);
  const wsql = where.length ? ' WHERE ' + where.join(' AND ') : '';
  const total = db().prepare(
    `SELECT COUNT(*) AS n FROM articles a${wsql}`).get(...params).n;
  const rows = db().prepare(
    `SELECT a.id, a.title, a.url, a.author, a.published_at, a.discovered_at, a.language,
            a.category, a.story_id, a.status, a.image_main_url,
            s.name AS source_name, s.slug AS source_slug
     FROM articles a JOIN sources s ON s.id = a.source_id${wsql}
     ORDER BY COALESCE(a.published_at, a.discovered_at) DESC LIMIT ? OFFSET ?`
  ).all(...params, limit, offset);
  return { total, limit, offset, results: rows };
}

function getArticle(id) {
  const a = db().prepare(
    `SELECT a.*, s.name AS source_name, s.slug AS source_slug, s.site_url
     FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.id = ?`).get(+id);
  if (!a) return null;
  delete a.raw_path;
  a.images = db().prepare(
    `SELECT id, original_url, content_hash, width, height, mime, main
     FROM images WHERE article_id = ?`).all(+id);   // [QA-9] 不暴露 local_path
  if (a.story_id) {
    a.story = db().prepare(
      `SELECT id, title, first_seen, last_updated, heat, importance, category, source_count
       FROM stories WHERE id = ?`).get(a.story_id) || null;
  }
  return a;
}

// ---------- stories ----------
function searchStories({ q, hours, category, limit, offset }) {
  limit = Math.min(+limit || 20, 50); offset = Math.max(+offset || 0, 0);
  const where = ["st.status = 'active'"]; const params = [];
  const fts = ftsQuery(q, 'or');
  let join = '';
  if (fts) { join = 'JOIN stories_fts ON stories_fts.rowid = st.id'; where.push('stories_fts MATCH ?'); params.push(fts); }
  if (hours) { where.push('st.last_updated >= ?'); params.push(isoAgo(+hours)); }
  if (category) { where.push('st.category = ?'); params.push(category); }
  const wsql = ' WHERE ' + where.join(' AND ');
  const total = db().prepare(
    `SELECT COUNT(*) AS n FROM stories st ${join}${wsql}`).get(...params).n;
  const order = fts ? 'ORDER BY bm25(stories_fts)' : 'ORDER BY st.last_updated DESC';
  const rows = db().prepare(
    `SELECT st.id, st.title, st.summary, st.first_seen, st.last_updated, st.heat, st.importance,
            st.category, st.language, st.article_count, st.source_count, st.video_count, st.status,
            st.fact_status, st.independent_source_count,
            st.ai_enhanced, st.ai_model, st.ai_at, st.ai_summary, st.ai_entities, st.ai_timeline,
            ${fts ? 'bm25(stories_fts) AS rank' : 'NULL AS rank'}
     FROM stories st ${join}${wsql} ${order} LIMIT ? OFFSET ?`
  ).all(...params, limit, offset);
  const artStmt = db().prepare(
    `SELECT a.id, a.title, a.url, a.published_at, a.image_main_url,
            s.name AS source_name, s.slug AS source_slug
     FROM articles a JOIN sources s ON s.id = a.source_id
     WHERE a.story_id = ? ORDER BY COALESCE(a.published_at, a.discovered_at) DESC LIMIT 6`);
  for (const st of rows) st.articles = artStmt.all(st.id);
  return { total, limit, offset, results: rows };
}

function getStory(id) {
  const st = db().prepare(`SELECT id,title,summary,first_seen,last_updated,heat,importance,category,language,
    article_count,source_count,video_count,status,fact_status,independent_source_count,
    ai_enhanced,ai_model,ai_at,ai_summary,ai_entities,ai_timeline FROM stories WHERE id = ?`).get(+id);   // [QA-8]
  if (!st) return null;
  const arts = db().prepare(
    `SELECT a.id, a.story_id, a.title, a.original_title, a.url, a.canonical_url, a.author, a.source_id,
            a.published_at, a.fetched_at, a.discovered_at, a.language, a.image_main_url, a.status,
            a.extract_method, a.summary_text,
            s.id AS s_id, s.name, s.slug AS source_slug, s.source_type, s.tier, s.quality_score, s.verification_status
     FROM story_articles sa JOIN articles a ON a.id = sa.article_id
     JOIN sources s ON s.id = a.source_id WHERE sa.story_id = ?
     ORDER BY COALESCE(a.published_at, a.discovered_at) ASC`).all(+id);
  st.articles = arts;
  st.timeline = arts.map((a) => toSearchEvidence(a));
  return st;
}

// ---------- trending / sources / categories ----------
function trending({ hours, category, limit }) {
  hours = +hours || 24; limit = Math.min(+limit || 20, 50);
  const params = [isoAgo(hours)];   // [QA-4] hours=活跃度窗口; window_hours 固定 24
  let wcat = '';
  if (category) { wcat = ' AND st.category = ?'; params.push(category); }
  return db().prepare(
    `SELECT t.score, st.id AS story_id, st.title, st.importance, st.category,
            st.article_count, st.source_count, st.first_seen, st.last_updated,
            st.entities, st.locations
     FROM trending t JOIN stories st ON st.id = t.story_id
     WHERE t.window_hours = 24 AND st.last_updated >= ?${wcat}
     ORDER BY t.score DESC LIMIT ?`).all(...params, limit);
}

function listSources() {
  return db().prepare(
    `SELECT s.id, s.slug, s.name, s.kind, s.site_url, s.feed_url, s.category, s.language,
            COALESCE(s.country, '') AS country, s.priority, s.poll_seconds, s.last_ok_at,
            s.consecutive_failures, s.disabled, s.items_total,
            (SELECT COUNT(*) FROM articles a WHERE a.source_id = s.id
               AND a.discovered_at >= datetime('now', '-24 hours')) AS articles_24h,
            (SELECT COUNT(*) FROM crawl_errors e WHERE e.source_id = s.id) AS error_count
     FROM sources s ORDER BY s.category, s.priority DESC, s.slug`).all();
}

function categories() {
  return db().prepare(
    `SELECT COALESCE(category, 'general') AS category, COUNT(*) AS n
     FROM articles GROUP BY category ORDER BY n DESC`).all();
}

function getImageMeta(id) {
  return db().prepare(
    `SELECT id, article_id, original_url, local_path, content_hash, mime, purged_at
     FROM images WHERE id = ?`).get(+id) || null;
}

function health() {
  const c = (sql, ...p) => db().prepare(sql).get(...p).n;
  const walExists = require('fs').existsSync(DB_PATH + '-wal');
  return {
    status: 'ok',
    articles_total: c('SELECT COUNT(*) AS n FROM articles'),
    articles_24h: c('SELECT COUNT(*) AS n FROM articles WHERE discovered_at >= ?', isoAgo(24)),
    articles_with_content: c('SELECT COUNT(*) AS n FROM articles WHERE content IS NOT NULL'),
    stories_active: c("SELECT COUNT(*) AS n FROM stories WHERE status = 'active'"),
    images_total: c('SELECT COUNT(*) AS n FROM images WHERE purged_at IS NULL'),
    sources_active: c('SELECT COUNT(*) AS n FROM sources WHERE disabled = 0'),
    tasks_pending: c("SELECT COUNT(*) AS n FROM crawl_tasks WHERE state = 'pending'"),
    errors_24h: c('SELECT COUNT(*) AS n FROM crawl_errors WHERE at >= ?', isoAgo(24)),
    last_run: (db().prepare("SELECT value FROM meta WHERE key = 'last_run'").get() || {}).value || null,
    wal: walExists,
  };
}

function diskStatus() {
  const fs = require('fs');
  const dataDir = path.dirname(DB_PATH);
  const out = { data_dir: dataDir, db_bytes: 0, wal_bytes: 0, shm_bytes: 0,
                images_files: 0, images_bytes: 0, cache_files: 0, cache_bytes: 0, data_files: 0 };
  const st = (p) => { try { return fs.statSync(p).size; } catch { return 0; } };
  out.db_bytes = st(DB_PATH); out.wal_bytes = st(DB_PATH + '-wal'); out.shm_bytes = st(DB_PATH + '-shm');
  const root = path.dirname(dataDir);          // dataDir=.../database → 根是 .../news-data
  const walk = (dir, tag, depth) => {
    if (depth > 3) return;
    let items;
    try { items = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const it of items) {
      const full = path.join(dir, it.name);
      if (it.isDirectory()) walk(full, tag, depth + 1);
      else {
        out.data_files += 1;
        const sz = st(full);
        if (tag === 'images') { out.images_files += 1; out.images_bytes += sz; }
        else if (tag === 'cache') { out.cache_files += 1; out.cache_bytes += sz; }
      }
    }
  };
  walk(path.join(root, 'images'), 'images', 0);
  walk(path.join(root, 'cache'), 'cache', 0);
  const total = out.db_bytes + out.wal_bytes + out.images_bytes + out.cache_bytes;
  const QUOTA = 3 * 1024 * 1024 * 1024;
  const pct = +(total / QUOTA * 100).toFixed(1);
  out.data_bytes = total;
  out.data_pct_of_3gb = pct;
  out.level = pct >= 85 ? 'emergency' : pct >= 70 ? 'high' : pct >= 50 ? 'warning' : 'normal';
  return out;
}


function searchEvents({ q, min_importance, hours, limit, offset, ai_only }) {
  limit = Math.min(+limit || 20, 50); offset = Math.max(+offset || 0, 0);
  const where = ["st.status='active'"]; const params = [];
  const fts = ftsQuery(q, 'or');
  if (fts) { where.push('stories_fts MATCH ?'); params.push(fts); }
  if (hours) { where.push('st.last_updated >= ?'); params.push(isoAgo(+hours)); }
  if (min_importance === 'CRITICAL') where.push("st.importance='major'");
  else if (min_importance === 'HIGH') where.push("st.importance IN ('high','major')");
  else if (min_importance === 'NOTABLE') where.push("st.importance IN ('normal','high','major')");
  if (ai_only) where.push('st.ai_enhanced = 1');
  let join = fts ? 'JOIN stories_fts ON stories_fts.rowid = st.id' : '';
  const wsql = ' WHERE ' + where.join(' AND ');
  const total = db().prepare(`SELECT COUNT(*) AS n FROM stories st ${join}${wsql}`).get(...params).n;
  const rows = db().prepare(`SELECT st.id, st.title, st.importance, st.category, st.fact_status,
    st.independent_source_count, st.heat, st.ai_enhanced, st.ai_model, st.ai_at,
    substr(st.ai_summary, 1, 400) AS ai_summary, st.first_seen, st.last_updated
    FROM stories st ${join}${wsql} ORDER BY st.heat DESC, st.last_updated DESC LIMIT ? OFFSET ?`
  ).all(...params, limit, offset);
  const ev = db().prepare(`SELECT COUNT(DISTINCT e.domain) AS n FROM event_evidence e
    WHERE e.story_id=? AND e.tier IN ('A','B') AND e.is_original=1`);
  const cnt = db().prepare(`SELECT COUNT(DISTINCT source_id) AS n FROM articles WHERE story_id=?`);   // [QA-5] 独立来源数
  for (const r of rows) { r.source_count = cnt.get(r.id).n; r.independent_fact_sources = ev.get(r.id).n; }
  return { total, limit, offset, results: rows };
}
function getEventDetail(id) {
  const st = db().prepare(`SELECT id,title,summary,first_seen,last_updated,heat,importance,category,language,
    article_count,source_count,video_count,status,fact_status,independent_source_count,
    ai_enhanced,ai_model,ai_at,ai_summary,ai_entities,ai_timeline FROM stories WHERE id=? AND status='active'`).get(id);   // [QA-8] 排除 fingerprint
  if (!st) return null;
  st.articles = db().prepare(`SELECT a.id, a.story_id, a.title, a.original_title, a.url, a.canonical_url,
    a.author, a.source_id, a.published_at, a.fetched_at, a.discovered_at, a.language,
    substr(COALESCE(a.summary_text, a.content), 1, 300) AS excerpt,
    COALESCE(length(a.content), 0) AS content_chars,   -- [R4-P0-A] 整数不拖正文
    a.extract_method, a.dupe_of,
    s.id AS s_id, s.name, s.slug, s.source_type, s.tier, s.quality_score, s.verification_status, s.country
    FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.story_id=?
    ORDER BY COALESCE(a.published_at, a.discovered_at) LIMIT 10`).all(id).map((r) => ({
    ...toSearchEvidence(r),   // [R4-P0-A] 消费 r.excerpt, 不再依赖已删列 a.summary_text/a.content
    content_chars: r.content_chars,
    source_name: r.source_name, slug: r.slug, country: r.country,   // 兼容旧字段
  }));
  st.evidence_domains = db().prepare(`SELECT domain, MAX(tier) AS tier, MIN(source_type) AS source_type, MAX(is_original) AS is_original
    FROM event_evidence WHERE story_id=? AND is_original=1 GROUP BY domain`).all(id);
  st.official_source_count = db().prepare(`SELECT COUNT(DISTINCT e.domain) FROM event_evidence e
    WHERE e.story_id=? AND e.tier='A' AND e.is_original=1`).get(id).n;
  st.fact_history = db().prepare(`SELECT fact_status, reason, at FROM story_fact_history
    WHERE story_id=? ORDER BY at`).all(id);
  return st;
}

// P1-1: 检索结果统一 Evidence 形状 (映射层, 零新存储; snippet 来自 FTS5 仍属 UNTRUSTED)
function toSearchEvidence(r, extra) {
  const ev = toEvidence(r, r);
  if (r.excerpt) ev.excerpt = String(r.excerpt);
  ev.snippet = (r.snippet || ev.excerpt || '').slice(0, 500);
  ev.untrusted = true;
  if (extra) Object.assign(ev, extra);
  return ev;
}

function storyEvidence(storyId, k = 3) {
  // Event -> Evidence -> Article -> Source 追溯 (每事件最多 k 条, 复用 P0-1 模型)
  return db().prepare(`SELECT a.id, a.story_id, a.title, a.original_title, a.url, a.canonical_url,
    a.author, a.source_id, a.published_at, a.fetched_at, a.discovered_at, a.language,
    a.summary_text, a.content, a.extract_method,
    s.id AS s_id, s.name, s.slug, s.source_type, s.tier, s.quality_score, s.verification_status
    FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.story_id=?
    ORDER BY COALESCE(a.published_at, a.discovered_at) LIMIT ?`).all(storyId, k)
    .map((r) => toSearchEvidence(r));
}

let _sqMap = null;
function sourceQualityMap() {
  // [QA-6] 102 行一次读入+缓存; 消掉每请求 160-240 次 LIKE
  if (_sqMap) return _sqMap;
  _sqMap = new Map();
  for (const r of db().prepare(`SELECT id, name, source_type, tier, quality_score, site_url, feed_url FROM sources WHERE disabled=0`).all()) {
    for (const u of [r.site_url, r.feed_url]) {
      if (!u) continue;
      try { _sqMap.set(new URL(u).hostname.replace(/^www\./, ''), { source_id: r.id, name: r.name, source_type: r.source_type, tier: r.tier, quality_score: r.quality_score }); } catch { /* */ }
    }
  }
  return _sqMap;
}

function sourceQualityByDomains(domains) {
  const m = sourceQualityMap(); const out = {};
  for (const d0 of domains) { if (!d0) continue; const d = String(d0).toLowerCase().replace(/^www\./, ''); if (m.has(d)) out[d0] = m.get(d); }
  return out;
}
module.exports = { sourceQualityByDomains, toSearchEvidence, storyEvidence, db, diskStatus, searchArticles, latestArticles, getArticle, searchStories, getStory,
  searchEvents, getEventDetail,
                   trending, listSources, categories, getImageMeta, health, isoAgo };
