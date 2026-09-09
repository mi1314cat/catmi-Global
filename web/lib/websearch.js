// lib/websearch.js — Web Search Provider 层（零 API Key 核心依赖）
// 架构: PRIMARY=SearXNG（配置 SEARXNG_URL 即启用, 可指向自建 VPS）; 内置 keyless 兜底:
// ddg_html / bing_html / gnews_rss / bing_news_rss / wikipedia
// 每次搜索记录 provider status/latency/error（降级不失败）; 结果统一去重。
'use strict';
const http = require('http');
const https = require('https');
const { URLSearchParams } = require('url');
const fs = require('fs');
const path = require('path');
const os = require('os');

const UA = 'Mozilla/5.0 (X11; FreeBSD) AppleWebKit/537.36 GlobalIntelligenceSearch/1.0';
const HOME = process.env.HOME || os.homedir();

function readEnvLocal(name) {
  try {
    for (const line of fs.readFileSync(path.join(HOME, 'news-project', 'env.local'), 'utf8').split('\n')) {
      const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.+)\s*$/);
      if (m && m[1] === name) return m[2].trim().replace(/^["']|["']$/g, '');
    }
  } catch (e) { /* not configured */ }
  return '';
}

function fetchText(url, { method = 'GET', body = null, headers = {}, timeout = 12000 } = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const mod = u.protocol === 'http:' ? http : https;
    const req = mod.request(u, {
      method, headers: Object.assign({ 'User-Agent': UA, 'Accept-Language': 'en,zh;q=0.8' }, headers),
      timeout,
    }, (res) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        const loc = new URL(res.headers.location, u).toString();
        res.resume();
        fetchText(loc, { method, body, headers, timeout }).then(resolve, reject);
        return;
      }
      let data = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { data += c; if (data.length > 3_000_000) req.destroy(); });
      res.on('end', () => resolve({ status: res.statusCode, text: data }));
    });
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

// ---------- URL/标题去重 ----------
function normalizeUrl(u) {
  try {
    const p = new URL(u);
    const keep = [];
    p.searchParams.forEach((v, k) => { if (!/^(utm_|fbclid|gclid|ref|cmpid)/i.test(k)) keep.push(k + '=' + v); });
    return p.origin.toLowerCase().replace(/^www\./, '') + p.pathname.replace(/\/$/, '') + (keep.length ? '?' + keep.join('&') : '');
  } catch { return u; }
}
const STOP = new Set(('the a an and or of to in on for with at by from as is are was were be been it its this that ' +
  'these those after before over under new says say said will would could news latest').split(' '));
function tokens(t) { return new Set((t.toLowerCase().match(/[a-z]{3,}/g) || []).filter((w) => !STOP.has(w))); }

function dedup(items) {
  const seenUrl = new Set(); const out = [];
  for (const it of items) {
    const nu = normalizeUrl(it.url);
    if (seenUrl.has(nu)) continue;
    seenUrl.add(nu);
    out.push(it);
  }
  // 标题近似去重（Jaccard≥0.8）
  const fin = [];
  const toks = [];
  for (const it of out) {
    const t = tokens(it.title || '');
    let dup = false;
    for (let i = 0; i < toks.length; i++) {
      let inter = 0; for (const w of t) if (toks[i].has(w)) inter++;
      const uni = t.size + toks[i].size - inter;
      if (uni && inter / uni >= 0.8) { dup = true; break; }
    }
    if (!dup) { fin.push(it); toks.push(t); }
  }
  return fin;
}

// ---------- Providers ----------
async function searxng(q, opts) {
  const base = readEnvLocal('SEARXNG_URL') || readEnvLocal('SEARX_BASE');
  if (!base) throw new Error('SEARXNG_URL not configured');
  const p = new URLSearchParams({ q, format: 'json', language: opts.language || 'en-US' });
  if (opts.time_range) p.set('time_range', opts.time_range);
  if (opts.category && opts.category !== 'general') p.set('categories', opts.category);
  if (opts.page > 1) p.set('pageno', String(opts.page));
  const r = await fetchText(base.replace(/\/$/, '') + '/search?' + p.toString(), { headers: { Accept: 'application/json' } });
  const d = JSON.parse(r.text);
  return (d.results || []).slice(0, opts.limit).map((x) => ({
    title: x.title, url: x.url, snippet: (x.content || '').slice(0, 300),
    source: (new URL(x.url)).hostname, published: x.publishedDate || null, provider: 'searxng',
  }));
}

function unwrapDdg(u) {
  try {
    if (u.includes('duckduckgo.com/l/')) {
      const p = new URL(u.startsWith('//') ? 'https:' + u : u);
      const t = p.searchParams.get('uddg');
      if (t) return decodeURIComponent(t);
    }
  } catch { /* keep */ }
  return u;
}

async function ddgHtml(q, opts) {
  const p = new URLSearchParams({ q, kl: opts.region_ddg || 'wt-wt', df: opts.time_range || '' });
  const r = await fetchText('https://html.duckduckgo.com/html/?' + p.toString(), {
    method: 'POST', body: new URLSearchParams({ q }).toString(),
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  if (r.status !== 200) throw new Error('HTTP ' + r.status);
  const out = [];
  const re = /<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g;
  let m;
  while ((m = re.exec(r.text)) && out.length < opts.limit) {
    const url = unwrapDdg(m[1]);
    if (!/^https?:/.test(url)) continue;
    const title = m[2].replace(/<[^>]+>/g, '').trim();
    const snipM = r.text.slice(m.index, m.index + 3000).match(/class="[^"]*result__snippet[^"]*"[^>]*>([\s\S]*?)<\/a>/);
    const snippet = snipM ? snipM[1].replace(/<[^>]+>/g, '').trim().slice(0, 300) : '';
    if (title) out.push({ title, url, snippet, source: new URL(url).hostname, published: null, provider: 'ddg' });
  }
  if (!out.length) throw new Error('0 results (bot-blocked?)');
  return out;
}

async function bingHtml(q, opts) {
  const p = new URLSearchParams({ q, setlang: (opts.language || 'en').split('-')[0], cc: opts.region || '' });
  const r = await fetchText('https://www.bing.com/search?' + p.toString());
  if (r.status !== 200) throw new Error('HTTP ' + r.status);
  const out = [];
  const re = /<li class="b_algo">[\s\S]*?<h2><a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a><\/h2>([\s\S]*?)<\/li>/g;
  let m;
  while ((m = re.exec(r.text)) && out.length < opts.limit) {
    const url = m[1].startsWith('http') ? m[1] : 'https://www.bing.com' + m[1];
    const title = m[2].replace(/<[^>]+>/g, '').trim();
    const snip = (m[3].match(/<p[^>]*>([\s\S]*?)<\/p>/) || [, ''])[1].replace(/<[^>]+>/g, '').trim().slice(0, 300);
    if (title && !url.includes('bing.com/acl')) out.push({ title, url, snippet: snip, source: new URL(url).hostname, published: null, provider: 'bing' });
  }
  if (!out.length) throw new Error('0 results (blocked?)');
  return out;
}

const LANG_MAP = { en: ['en-US', 'en-US'], zh: ['zh-CN', 'zh-CN'], ja: ['ja', 'ja-JP'], ko: ['ko', 'ko-KR'],
                  ru: ['ru', 'ru-RU'], fr: ['fr', 'fr-FR'], de: ['de', 'de-DE'], es: ['es', 'es-ES'], ar: ['ar', 'ar-AE'] };

async function gnewsRss(q, opts) {
  const [hl, ceidPair] = LANG_MAP[opts.language] || ['en-US', 'en-US'];
  const when = { day: 'when:1d', week: 'when:7d', month: 'when:1m', year: 'when:1y' }[opts.time_range] || '';
  const term = when ? `${q} ${when}` : q;
  const p = new URLSearchParams({ q: term, hl, gl: ceidPair.split('-')[1], ceid: `${ceidPair.replace('-', ':')}` });
  const r = await fetchText('https://news.google.com/rss/search?' + p.toString(), { timeout: 15000 });
  if (r.status !== 200) throw new Error('HTTP ' + r.status);
  const out = [];
  const re = /<item>[\s\S]*?<title>(?:<!\[CDATA\[)?([^<\]]*)(?:\]\]>)?<\/title><link>([^<]+)<\/link>[\s\S]*?<pubDate>([^<]+)<\/pubDate>/g;
  let m;
  while ((m = re.exec(r.text)) && out.length < opts.limit) {
    const title = m[1].replace(/\s+-\s+[^-]{2,40}$/, '').trim();
    out.push({ title, url: m[2].trim(), snippet: '', source: 'news.google.com', published: new Date(m[3]).toISOString(), provider: 'gnews' });
  }
  if (!out.length) throw new Error('0 results');
  return out;
}

async function bingNewsRss(q, opts) {
  const p = new URLSearchParams({ q, format: 'RSS' });
  const r = await fetchText('https://www.bing.com/news/search?' + p.toString(), { timeout: 15000 });
  if (r.status !== 200) throw new Error('HTTP ' + r.status);
  const out = [];
  const re = /<item>[\s\S]*?<title>(?:<!\[CDATA\[)?([^<\]]*?)(?:\]\]>)?<\/title><link>([^<]+)<\/link>[\s\S]*?<pubDate>([^<]+)<\/pubDate>/g;
  let m;
  while ((m = re.exec(r.text)) && out.length < opts.limit) {
    let url = m[2].trim();
    try { // bing 跳转链接解包 url= 参数
      const u = new URL(url);
      const inner = u.searchParams.get('url');
      if (inner && inner.startsWith('http')) url = inner;
    } catch { /* keep */ }
    out.push({ title: m[1].trim(), url, snippet: '', source: new URL(url).hostname, published: new Date(m[3]).toISOString(), provider: 'bingnews' });
  }
  if (!out.length) throw new Error('0 results');
  return out;
}

async function wikipedia(q, opts) {
  const lang = (opts.language || 'en').split('-')[0];
  const p = new URLSearchParams({ action: 'opensearch', search: q, limit: '3', namespace: '0', format: 'json' });
  const r = await fetchText(`https://${lang}.wikipedia.org/w/api.php?` + p.toString(), { timeout: 8000 });
  if (r.status !== 200) throw new Error('HTTP ' + r.status);
  const d = JSON.parse(r.text);
  const titles = d[1] || []; const urls = d[3] || []; const descs = d[2] || [];
  return titles.map((t, i) => ({
    title: t, url: urls[i], snippet: (descs[i] || '').slice(0, 300),
    source: `${lang}.wikipedia.org`, published: null, provider: 'wikipedia',
  })).filter((x) => x.url);
}

// ---------- 统一入口 ----------
const PROVIDERS = {
  searxng: { fn: searxng, priority: 1, note: 'PRIMARY（配置 SEARXNG_URL 后启用）' },
  ddg: { fn: ddgHtml, priority: 2, note: 'keyless HTML' },
  bing: { fn: bingHtml, priority: 3, note: 'keyless HTML' },
  gnews: { fn: gnewsRss, priority: 4, note: 'keyless RSS（news 类最稳）' },
  bingnews: { fn: bingNewsRss, priority: 5, note: 'keyless RSS' },
  wikipedia: { fn: wikipedia, priority: 6, note: '实体参考' },
};

async function webSearch(query, opts = {}) {
  const limit = Math.min(Math.max(1, +opts.limit || 8), 20);
  const page = Math.max(1, +opts.page || 1);
  const o = { limit: limit + 4, language: opts.language, region: opts.region, time_range: opts.time_range, category: opts.category, page };
  const wanted = opts.providers
    ? opts.providers.split(',').map((s) => s.trim()).filter((s) => PROVIDERS[s])
    : Object.keys(PROVIDERS);
  const t0 = Date.now();
  const settled = await Promise.allSettled(
    wanted.map((name) => PROVIDERS[name].fn(query, o).then((rs) => ({ name, results: rs }))));
  const providers = [];
  let items = [];
  settled.forEach((s, i) => {
    const name = wanted[i];
    const latency_ms = Date.now() - t0;
    if (s.status === 'fulfilled' && s.value.results.length) {
      items.push(...s.value.results);
      providers.push({ provider: name, status: 'ok', latency_ms, count: s.value.results.length });
    } else {
      const err = s.status === 'rejected' ? String(s.reason && s.reason.message || s.reason).slice(0, 120)
        : (s.status === 'fulfilled' ? 'empty' : 'unknown');
      providers.push({ provider: name, status: 'error', error: err, latency_ms });
    }
  });
  items = dedup(items).slice(0, limit);
  return {
    query, scope: 'web', limit, page,
    elapsed_ms: Date.now() - t0,
    providers,
    results: items,
  };
}

function searchConfigured() {
  return { primary: readEnvLocal('SEARXNG_URL') ? 'searxng(self-hosted/configured)' : 'keyless providers (ddg/bing/gnews/bingnews/wikipedia)',
           searxng_url: !!readEnvLocal('SEARXNG_URL') };
}

module.exports = { webSearch, searchConfigured, dedup };
