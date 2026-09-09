// lib/query.js — Unified Query Service（REST / MCP / Web UI 共享同一套查询逻辑）
// scope: web = 互联网 | intelligence = 本地情报库 | all = 两者
'use strict';
const newsdb = require('./newsdb');
const websearch = require('./websearch');

async function search(query, opts = {}) {
  const scope = ['web', 'intelligence', 'all'].includes(opts.scope) ? opts.scope : 'all';
  const limit = Math.min(Math.max(1, +opts.limit || 10), 20);
  const out = { query, scope, limit };
  const jobs = [];
  if (scope === 'web' || scope === 'all') {
    jobs.push(websearch.webSearch(query, { limit: scope === 'all' ? Math.min(limit, 10) : limit,
      time_range: opts.time_range, language: opts.language, region: opts.region,
      category: opts.category, page: opts.page })
      .then((r) => { out.web = r; })
      .catch((e) => { out.web = { results: [], providers: [{ provider: 'all', status: 'error', error: String(e.message).slice(0, 120) }] }; }));
  }
  if (scope === 'intelligence' || scope === 'all') {
    jobs.push(new Promise((resolve) => {
      const arts = newsdb.searchArticles({ q: query, hours: opts.hours, category: opts.category,
        language: opts.language, sort: opts.sort, limit: scope === 'all' ? Math.min(limit, 10) : limit,
        offset: opts.offset });
      const stories = newsdb.searchStories({ q: query, hours: opts.hours, category: opts.category, limit: 5 });
      out.intelligence = {
        articles: arts, stories: { total: stories.total, results: stories.results },
      };
      resolve();
    }));
  }
  await Promise.all(jobs);
  return out;
}

// deep_search: 非研究型多跳（无 AI 依赖, 确定性编排, 时间预算内）
// web_search → 取 top 来源 → read_url(≤2, 预算内) → intelligence 关联 → 结构化研究包
async function deepSearch(query, opts = {}, reader) {
  const budgetMs = Math.min(+opts.budget_ms || 40000, 60000);
  const t0 = Date.now();
  const out = { query, steps: [], elapsed_ms: 0 };
  const ws = await websearch.webSearch(query, { limit: 10, time_range: opts.time_range, language: opts.language, category: opts.category || 'general' });
  out.steps.push({ step: 'web_search', providers: ws.providers, results: ws.results.length });
  const seen = new Set();
  const picks = [];
  for (const r of ws.results) {
    if (seen.has(r.source) && picks.length) continue;   // 每域先保 1 个来源（交叉验证优先多源）
    seen.add(r.source); picks.push(r);
    if (picks.length >= (opts.max_pages || 3)) break;
  }
  out.sources_picked = picks.map((p) => ({ provider: p.provider, source: p.source, title: p.title, url: p.url }));
  // 读取页面（预算内, 顺序, 每页硬超时 20s）
  out.pages = [];
  for (const p of picks) {
    if (Date.now() - t0 > budgetMs) { out.steps.push({ step: 'read_url', note: 'budget exceeded — skipped remaining' }); break; }
    try {
      const pg = await reader.readUrl(p.url, 20000);
      out.pages.push({ url: p.url, source: p.source, title: pg.title, status: pg.status,
        content_chars: pg.content_chars, excerpt: (pg.content || '').slice(0, 1200),
        published: pg.published, author: pg.author, method: pg.method });
    } catch (e) {
      out.pages.push({ url: p.url, status: 'failed', error: String(e.message).slice(0, 100) });
    }
  }
  // 情报库关联
  const arts = newsdb.searchArticles({ q: query, limit: 8 });
  const stories = newsdb.searchStories({ q: query, limit: 3 });
  out.intelligence_matches = { articles: { total: arts.total, results: arts.results }, stories: { total: stories.total, results: stories.results.map((s) => ({ id: s.id, title: s.title, article_count: s.article_count, source_count: s.source_count, last_updated: s.last_updated })) } };
  out.steps.push({ step: 'intelligence_search', articles: arts.total, stories: stories.total });
  out.elapsed_ms = Date.now() - t0;
  return out;
}

module.exports = { search, deepSearch };
