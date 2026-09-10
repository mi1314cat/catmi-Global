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

function fetchText(url, { method = 'GET', body = null, headers = {}, timeout = 12000, depth = 0, maxBytes = 1_000_000 } = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const mod = u.protocol === 'http:' ? http : https;
    const req = mod.request(u, {
      method, headers: Object.assign({ 'User-Agent': UA, 'Accept-Language': 'en,zh;q=0.8' }, headers),
      timeout,
    }, (res) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        const loc = new URL(res.headers.location, u).toString();
        if (depth > 5) { reject(new Error('redirect depth > 5')); return; }   // [QA-2] 重定向环防护
        res.resume();
        fetchText(loc, { method, body, headers, timeout, depth: depth + 1, maxBytes }).then(resolve, reject);
        return;
      }
      let data = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { data += c; if (data.length > maxBytes) req.destroy(); });   // [QA-11] 1MB 默认
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
function tokens(t) { return new Set((((t || '').toLowerCase().match(/[a-z]{3,}/g) || []).filter((w) => !STOP.has(w))).concat((t || '').match(/[\u4e00-\u9fff]|\u3040-\u30ff/g) || [])); }  // 拉丁词 + CJK 单字

// P0-2: 统一 SearchResult —— 所有后端出口必须经此归一化
function normResult(x, backend, rank, language) {
  const host = x.source || (x.url ? (new URL(x.url)).hostname : '');
  return {
    title: x.title || '',
    url: x.url || '',
    canonical_url: normalizeUrl(x.url || ''),
    source: host,
    source_id: null,                       // P0-3 由调用方按 domain 查 sources 表填充
    snippet: (x.snippet || '').slice(0, 300),
    published_at: x.published || x.publishedDate || null,   // 引擎给出的发布时间; 无则留给 P0-6 链
    published_at_source: x.published || x.publishedDate ? `engine.${backend}` : null,
    language: language || '',
    backend,
    rank: rank,                            // 后端原始排名位(0起)
    provider: backend,                     // 向后兼容别名
  };
}

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
  return (d.results || []).slice(0, opts.limit).map((x, i) => normResult({
    title: x.title, url: x.url, snippet: (x.content || '').slice(0, 300),
    published: x.publishedDate || null,
  }, 'searxng', i, opts.language));
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
  const p = new URLSearchParams({ q, kl: opts.region_ddg || opts.region || 'wt-wt', df: opts.time_range || '' });
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
    if (title) out.push(normResult({ title, url, snippet }, 'ddg', out.length, opts.language));
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
    if (title && !url.includes('bing.com/acl')) out.push(normResult({ title, url, snippet: snip }, 'bing', out.length, opts.language));
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
  const re = /<item>[\s\S]*?<\/item>/g;
  const tf = /<title>(?:<!\[CDATA\[)?([^<\]]*)(?:\]\]>)?<\/title>/;
  const lf = /<link>([^<]+)<\/link>/;
  const pf = /<pubDate>([^<]+)<\/pubDate>/;
  const sf = /<source url="([^"]+)">/;
  const gf = /<description>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/description>/;
  let m;
  while ((m = re.exec(r.text)) && out.length < opts.limit) {
    const it = m[0];
    const tm = it.match(tf); if (!tm) continue;
    const lm = it.match(lf); if (!lm) continue;
    const pm = it.match(pf); if (!pm) continue;
    const gm = it.match(gf);
    const title = tm[1].replace(/\s+-\s+[^-]{2,40}$/, '').trim();
    // [R2-03] gnews description 是实体转义的 HTML: 先解实体再剥标签, 否则 snippet=噪声且污染打分
    const snip = gm ? gm[1]
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&')
      .replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim().slice(0, 200) : '';
    // 真实出版方域名来自 <source url=""> (gnews 链接本身是重定向)
    const sm = it.match(sf);
    const pubUrl = sm ? sm[1] : '';
    const pubHost = pubUrl ? (new URL(pubUrl)).hostname.replace(/^www\./, '') : '';
    const x = normResult({ title, url: lm[1].trim(), snippet: snip, published: new Date(pm[1]).toISOString() }, 'gnews', out.length, opts.language);
    if (pubHost) { x.publisher_domain = pubHost; x.canonical_url = pubUrl; x.source = pubHost; }
    out.push(x);
  }
  if (!out.length) throw new Error('0 results');
  return out;
}

async function bingNewsRss(q, opts) {
  const p = new URLSearchParams({ q, format: 'RSS' });
  const r = await fetchText('https://www.bing.com/news/search?' + p.toString(), { timeout: 15000 });
  if (r.status !== 200) throw new Error('HTTP ' + r.status);
  const out = [];
  const re = /<item>[\s\S]*?<\/item>/g;   // [QA-1] item-slice: &amp; 解码 + 真实域名 + description snippet
  const tf = /<title>(?:<!\[CDATA\[)?([^<\]]*?)(?:\]\]>)?<\/title>/;
  const df = /<description>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/description>/;
  const pf = /<pubDate>([^<]+)<\/pubDate>/;
  let m;
  while ((m = re.exec(r.text)) && out.length < opts.limit) {
    const it = m[0];
    const tm = it.match(tf); if (!tm) continue;
    const pm = it.match(pf); if (!pm) continue;
    const dm = it.match(df);
    let url = ((it.match(/<link>([^<]+)<\/link>/) || [])[1] || '').trim().replace(/&amp;/g, '&');  // 关键: 解码实体
    let pubHost = '';
    try {
      const u = new URL(url);
      const inner = u.searchParams.get('url') || u.searchParams.get('u');
      if (inner && /^https?:/.test(inner)) { url = inner; pubHost = new URL(url).hostname.replace(/^www\./, ''); }
    } catch { /* keep */ }
    const snip = dm ? dm[1].replace(/<[^>]+>/g, '').trim().slice(0, 300) : '';
    const x = normResult({ title: tm[1].trim(), url, snippet: snip, published: new Date(pm[1]).toISOString() }, 'bingnews', out.length, opts.language);
    if (pubHost) { x.publisher_domain = pubHost; x.canonical_url = url; x.source = pubHost; }
    out.push(x);
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
  return titles.map((t, i) => normResult({
    title: t, url: urls[i], snippet: (descs[i] || '').slice(0, 300), source: `${lang}.wikipedia.org`,
  }, 'wikipedia', i, opts.language)).filter((x) => x.url);
}

// ---------- P1-3: Query Intent 规则路由 (可解释, 零 AI) ----------
const INTENT_RULES = [
  ['NEWS', /最新|突发|今天|今日|本周|刚刚|实时|财报|breaking|latest|\bnews\b|just\s+in/i],
  ['EVENT', /事件|时间线|发生了什么|袭击|爆炸|空袭|枪击|停火|制裁|关税|谈判|地震|洪水|判决|outbreak|attack|protest|election|strike|war|\btimeline\b/i],
  ['OFFICIAL', /官方|官网|政策|商务部|政府|部门|声明|official|\bdocs?\b|api\s+reference|pricing|changelog|release\s+notes|\bgov\b|ministry|statement/i],
  ['TECH', /\b(cpu|gpu|api|model|framework|linux|python|javascript)\b|算法|模型|开源|\brepo\b|github|stack\s+trace|\bcode\b/i],
  ['RESEARCH', /论文|综述|研究报告|\bpaper\b|arxiv|\bstudy\b|\bsurvey\b/i],
];
function detectIntent(q) {
  const hit = [];
  for (const [name, re] of INTENT_RULES) if (re.test(String(q || ''))) hit.push(name);
  const intent = hit[0] || 'GENERAL';
  // intent → 重排权重调整 (NEWS 提新鲜度; OFFICIAL 提官方)
  const weights = intent === 'NEWS' ? { rel: 0.40, fr: 0.35, q: 0.15, off: 0.10 }
    : intent === 'OFFICIAL' ? { rel: 0.40, fr: 0.20, q: 0.20, off: 0.20 }
    : { rel: 0.45, fr: 0.25, q: 0.20, off: 0.10 };
  return { intent, rules_hit: hit, weights };
}

// ---------- P0-3: 规则重排 ----------
const OFFICIAL_TLD = /\.(gov|edu|mil|int)(\.[a-z]{2,3})?$/i;
const OFFICIAL_PATH = /\/(docs?|api|pricing|changelog|releases?|press|policy)(\/|$)/i;

function relevanceScore(qTokens, item) {
  if (!qTokens.size) return 0;
  const doc = tokens((item.title || '') + ' ' + (item.snippet || ''));
  let hit = 0; for (const w of qTokens) if (doc.has(w)) hit++;
  return hit / qTokens.size;               // query 词覆盖率
}

function freshnessScore(publishedAt, halfLifeH) {
  if (!publishedAt) return 0;
  const dt = (Date.now() - Date.parse(publishedAt)) / 3600000;
  if (!isFinite(dt) || dt < 0 || dt > 24 * 365 * 3) return 0;  // 超过3年=0, 未来时间=0
  return Math.exp(-dt / halfLifeH);
}

function officialScore(item, q) {
  const host = (item.source || '').toLowerCase();
  const url = item.url || item.canonical_url || '';
  let v = 0;
  if (OFFICIAL_TLD.test(host)) v = 1;                       // .gov/.edu/.mil/.int
  else if (OFFICIAL_PATH.test(url)) v = 0.8;                // /docs /api /pricing /changelog
  else if (/^(www\.)?(reuters|apnews|afp|bbc|aljazeera)\./.test(host)) v = 0.5; // 通讯社
  const sq = (q || '').toLowerCase();
  if ((sq.includes('official') || sq.includes('官方') || sq.includes('pricing') || sq.includes('官网')) && url && !/news|blog|forum|reddit/.test(url)) v = Math.max(v, 0.7);
  return v;
}

function seoFarmPenalty(item, rel) {
  // 保守: 仅当 无摘要 + 相关性极低 + 无发布时间 才轻降权 (模板垃圾特征), 不猜新域名
  if (!item.snippet && rel < 0.15 && !item.published_at) return 0.35;
  return 0;
}

// resolver: domain -> {quality_score, tier, source_type} | null (调用方注入, websearch 保持无 DB 依赖)
function rerank(items, query, opts) {
  const qTokens = tokens(query || '');
  const halfLifeH = { day: 24, week: 72, month: 240, year: 720 }[opts.time_range] || 72;
  const res = opts.source_quality || (() => null);
  for (const it of items) {
    const rel = relevanceScore(qTokens, it);
    const fr = freshnessScore(it.published_at, halfLifeH);
    const dom = (it.publisher_domain || it.source || '').replace(/^www\./, '');
    const sq = res(dom) || res(it.source || '') || null;
    const AGG = /^(msn\.com|news\.google\.com|bing\.com)$/.test(dom);   // [R2-5.2] dom 已去 www, 精简死分支
    const q01 = AGG ? 0.15 : (sq && sq.quality_score != null ? Math.max(0, Math.min(100, sq.quality_score)) / 100 : 0.4);
    const off = officialScore(it, query);
    const penalty = seoFarmPenalty(it, rel) + (AGG ? 0.05 : 0);
    const W = opts.intent_weights || { rel: 0.35, fr: 0.25, q: 0.30, off: 0.10 };   // [QA-13] quality 0.2→0.3
    const final = W.rel * rel + W.fr * fr + W.q * q01 + W.off * off - penalty;
    it.relevance_score = +rel.toFixed(3);
    it.freshness_score = +fr.toFixed(3);
    it.source_quality_score = sq ? sq.quality_score : null;
    it.source_tier = sq ? sq.tier : null;
    it.source_type = sq ? sq.source_type : it.source_type || null;
    it.source_id = sq ? sq.source_id : null;                 // P0-2 留空的 source_id 在此回填
    it.official_score = +off.toFixed(2);
    it.final_score = +final.toFixed(3);
    it.score_breakdown = { relevance: it.relevance_score, freshness: it.freshness_score, quality: +q01.toFixed(2), official: it.official_score, penalty };
  }
  items.sort((a, b) => b.final_score - a.final_score);
  // [QA-14] time_range 硬过滤 (provider 不支持也保证窗口正确)
  const WINDOW_H = { day: 24, week: 168, month: 720, year: 8760 }[opts.time_range];
  const inWin = []; const outWin = [];
  for (const it of items) {
    if (WINDOW_H && it.published_at) {
      const ageH = (Date.now() - Date.parse(it.published_at)) / 3600000;
      if (isFinite(ageH) && ageH > WINDOW_H) { it.filtered_reason = `out_of_window>${opts.time_range}`; outWin.push(it); continue; }
    }
    inWin.push(it);
  }
  items = inWin;   // [R2-01] filtered 合并移到 return (修复未定义崩溃)
  // Diversity: 同域≤2 (publisher_domain/source), 超出移入 filtered 保留
  const cap = Math.max(1, +opts.domain_cap || 2);
  const cnt = {}; const main = []; const filtered2 = [];
  for (const it of items) {
    const d = (it.publisher_domain || it.source || 'unknown').replace(/^www\./, '');
    cnt[d] = (cnt[d] || 0) + 1;
    (cnt[d] <= cap ? main : filtered2).push(it);
    if (cnt[d] > cap) it.filtered_reason = `domain_cap:${d}`;
  }
  return { main, filtered: outWin.concat(filtered2) };   // [R2-01]
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
  const intentInfo = detectIntent(query);
  const time_range = opts.time_range || (intentInfo.intent === 'NEWS' ? 'week' : undefined);
  const o = { limit: limit + 4, language: opts.language, region: opts.region, time_range, category: opts.category, page, intent_weights: intentInfo.weights };
  const wanted = opts.providers
    ? opts.providers.split(',').map((s) => s.trim()).filter((s) => PROVIDERS[s])
    : Object.keys(PROVIDERS);
  const t0 = Date.now();
  // [R2-06] Promise.all + 内部 catch: 失败 provider 也有真实 latency
  const settled = await Promise.all(
    wanted.map(async (name) => {
      const t = Date.now();
      try {
        const rs = await PROVIDERS[name].fn(query, o);
        return { name, results: rs, latency_ms: Date.now() - t };
      } catch (e) {
        return { name, error: String((e && e.message) || e).slice(0, 120), latency_ms: Date.now() - t };
      }
    }));
  const providers = [];
  let items = [];
  for (const s of settled) {
    if (s.results && s.results.length) {
      items.push(...s.results);
      providers.push({ provider: s.name, status: 'ok', latency_ms: s.latency_ms, count: s.results.length });
    } else {
      providers.push({ provider: s.name, status: 'error', error: s.error || 'empty', latency_ms: s.latency_ms });
    }
  }
  items = dedup(items);
  const unranked = items.slice();                          // 旧顺序(诊断对比用)
  const { main, filtered } = rerank(items, query, opts);
  items = main.slice(0, limit);
  return {
    query, scope: 'web', limit, page,
    intent: { intent: intentInfo.intent, rules_hit: intentInfo.rules_hit },
    elapsed_ms: Date.now() - t0,
    providers,
    results: items,
    filtered: filtered.slice(0, 8),            // 被多样性截断的结果(带 filtered_reason) 保留 debug
    unranked_first3: unranked.slice(0, 3).map((x) => x.source + '|' + (x.title || '').slice(0, 40)),  // 旧顺序对照
  };
}

function searchConfigured() {
  return { primary: readEnvLocal('SEARXNG_URL') ? 'searxng(self-hosted/configured)' : 'keyless providers (ddg/bing/gnews/bingnews/wikipedia)',
           searxng_url: !!readEnvLocal('SEARXNG_URL') };
}

module.exports = { webSearch, searchConfigured, dedup };
