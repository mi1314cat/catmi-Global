// app.js — <你的域名> 服务层（Phase 4 REST API + Phase 5 MCP + Phase 7 Web UI）
// Passenger Node 22 · 零框架 · 只读 SQLite · AI 不在链路 · 无任何秘密硬编码
'use strict';
const http = require('http');
const path = require('path');
const fs = require('fs');
const newsdb = require('./lib/newsdb');
const querysvc = require('./lib/query');
const reader = require('./lib/reader');
const websearch = require('./lib/websearch');
const auth = require('./lib/auth');
const adminsvc = require('./lib/admin');

const PORT = Number(process.env.PORT || 3000);
const PUBLIC_DIR = path.join(__dirname, 'public');
const SITE_ORIGIN = 'https://<你的域名>';

// ---- Token 从 env.local 读取（chmod 600; 绝不打印/落日志） ----
function readToken(name) {
  try {
    const p = path.join(process.env.HOME || os.homedir(), 'news-project', 'env.local');
    for (const line of fs.readFileSync(p, 'utf8').split('\n')) {
      const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.+)\s*$/);
      if (m && m[1] === name) return m[2].trim().replace(/^["']|["']$/g, '');
    }
  } catch (e) { /* 无文件=未配置 */ }
  return '';
}
function os_homedir() { return require('os').homedir(); }
const MCP_TOKEN = readToken('MCP_TOKEN');
const MCP_TOOL_NAMES = ['search_news', 'search_events', 'get_event', 'get_article', 'get_trending',
  'search_media', 'get_timeline', 'list_sources', 'web_search', 'read_url',
  'search_intelligence', 'deep_search'];       // Phase 5 启用
const AI_HINT = null;                            // AI 永不进本进程

// ---- 简单限速（内存; 进程重启即清零——可接受） ----
const RATE = { api: { n: 120, windowMs: 60000 }, mcp: { n: 60, windowMs: 60000 } };
const hits = new Map();
function rateLimited(bucket, ip) {
  const now = Date.now();
  const key = bucket + '|' + ip;
  const rec = hits.get(key);
  if (!rec || now > rec.reset) { hits.set(key, { n: 1, reset: now + RATE[bucket].windowMs }); return false; }
  rec.n += 1;
  return rec.n > RATE[bucket].n;
}

// ---- 请求日志（脱敏: 不记 query 里的 token; 不记 body） ----
function logLine(obj) {
  try {
    const dir = path.join(process.env.HOME || os.homedir(), 'news-project', 'news-data', 'logs');
    fs.mkdirSync(dir, { recursive: true });
    const f = path.join(dir, 'web.log');
    if (fs.existsSync(f) && fs.statSync(f).size > 5 * 1024 * 1024) {
      fs.renameSync(f, f + '.1');
    }
    fs.appendFileSync(f, JSON.stringify(obj) + '\n');
  } catch (e) { /* 日志失败不影响服务 */ }
}

function send(res, code, obj, headers) {
  const body = obj === null ? '' : JSON.stringify(obj);
  res.writeHead(code, Object.assign({
    'Content-Type': 'application/json; charset=utf-8',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
  }, headers || {}));
  res.end(body);
}

function serveStatic(res, file) {
  const full = path.normalize(path.join(PUBLIC_DIR, file));
  if (!full.startsWith(PUBLIC_DIR) || !fs.existsSync(full) || !fs.statSync(full).isFile()) {
    res.writeHead(404); res.end('not found'); return;
  }
  const ext = path.extname(full);
  const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css',
                 '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon' }[ext]
                 || 'application/octet-stream';
  res.writeHead(200, { 'Content-Type': mime, 'Cache-Control': 'public, max-age=300' });
  fs.createReadStream(full).pipe(res);
}

function serveImage(res, id) {
  const meta = newsdb.getImageMeta(id);
  if (!meta || meta.purged_at || !meta.local_path) { send(res, 404, { error: 'not found' }); return; }
  const full = path.normalize(meta.local_path);
  const imgDir = path.join(process.env.HOME || os_homedir(), 'news-project', 'news-data', 'images');
  if (!full.startsWith(imgDir) || !fs.existsSync(full)) { send(res, 404, { error: 'not found' }); return; }
  res.writeHead(200, { 'Content-Type': meta.mime || 'image/jpeg',
                       'Cache-Control': 'public, max-age=3600', 'X-Content-Type-Options': 'nosniff' });
  fs.createReadStream(full).pipe(res);
}

// ---------- 管理路由 ----------
async function handleAdmin(req, res, url, sess) {
  const q = url.searchParams;
  const p = url.pathname.replace(/^\/api\/admin/, '');
  const ok = (o) => send(res, 200, o);
  let m;
  if (p === '/overview') {
    const h = newsdb.health();
    return ok({ ...h, disk: newsdb.diskStatus(), mcp: { enabled: !!mcpHandler, tools: mcpHandler ? MCP_TOOL_NAMES.length : 0 },
      web_search: websearch.searchConfigured(), time: new Date().toISOString() });
  }
  if (p === '/diagnostics') return ok(await adminsvc.diagnostics());
  if (p === '/mcp/test') return ok(await adminsvc.mcpSelfTest());
  if (p === '/mcp/tokens') return ok({ results: auth.listMcpTokens() });
  if (p === '/mcp/tokens' && false) return ok();
  if ((m = p.match(/^\/mcp\/tokens\/(\d+)$/)) && req.method === 'POST') {
    const chunks = []; for await (const c of req) chunks.push(c);
    let body = {}; try { body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); } catch { /* */ }
    return ok(auth.mcpTokenAction(+m[1], body.action));
  }
  if (p === '/mcp/tokens/create' && req.method === 'POST') {
    const chunks = []; for await (const c of req) chunks.push(c);
    let body = {}; try { body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); } catch { /* */ }
    return ok(auth.createMcpToken(body.name));
  }
  if (p === '/users') return ok({ results: auth.listUsers() });
  if (p === '/users/create' && req.method === 'POST') {
    const chunks = []; for await (const c of req) chunks.push(c);
    let b = {}; try { b = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); } catch { /* */ }
    return ok(auth.createUser(b.username, b.password, b.role || 'user'));
  }
  if ((m = p.match(/^\/users\/(\d+)$/)) && req.method === 'POST') {
    const chunks = []; for await (const c of req) chunks.push(c);
    let b = {}; try { b = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); } catch { /* */ }
    if (b.action === 'reset') return ok(auth.resetUserPassword(+m[1], b.password));
    return ok(auth.setUserEnabled(+m[1], b.action === 'enable'));
  }
  if ((m = p.match(/^\/sources\/(\d+)$/)) && req.method === 'POST') {
    const chunks = []; for await (const c of req) chunks.push(c);
    let b = {}; try { b = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); } catch { /* */ }
    const col = newsdb.db && null; // 占位防误用
    const wdb = adminWriteDb();
    if (b.action === 'enable' || b.action === 'disable') {
      wdb.prepare('UPDATE sources SET disabled=?, disabled_reason=? WHERE id=?')
        .run(b.action === 'disable' ? 1 : 0, b.action === 'disable' ? 'admin-disabled' : null, +m[1]);
      auth.audit(sess.username, 'source-' + b.action, 'id=' + m[1]);
      return ok({ ok: true });
    }
    return send(res, 400, { error: 'unknown action' });
  }
  if ((m = p.match(/^\/sources\/(\d+)\/test$/)) && req.method === 'POST') {
    const slug = adminSourceSlug(+m[1]);
    if (!slug) return send(res, 404, { error: 'source not found' });
    try {
      const r = await adminRunPython(['-m', 'news.source_test', slug], 40000);
      return ok(typeof r === 'object' ? r : { raw: String(r).slice(0, 400) });
    } catch (e) { return send(res, 500, { error: String(e.message).slice(0, 150) }); }
  }
  if ((m = p.match(/^\/sources\/(\d+)$/)) && req.method === 'DELETE') {
    const wdb = adminWriteDb();
    wdb.prepare('UPDATE articles SET story_id=NULL WHERE source_id=?').run(+m[1]);
    wdb.prepare('DELETE FROM sources WHERE id=?').run(+m[1]);
    auth.audit(sess.username, 'source-delete', 'id=' + m[1]);
    return ok({ ok: true, note: '来源已删除（已采集文章保留）' });
  }
  if (p === '/logs') {
    return ok({ web: adminsvc.tailLog('web.log', 40), cron: adminsvc.tailLog('cron.log', 30), audit: auth.tailAudit(40) });
  }
  if (p === '/settings') return ok(adminsvc.settings());
  return send(res, 404, { error: 'unknown admin endpoint' });
}

// 管理面写库: 独立可写连接（只允许 sources 表的运营操作; 管道 Cron 兼容 WAL 多写需 busy_timeout——已设置）
let _wdb = null;
function adminWriteDb() {
  if (!_wdb) {
    const { DatabaseSync } = require('node:sqlite');
    const dbp = path.join(process.env.HOME || os.homedir(), 'news-project', 'news-data', 'database', 'news.db');
    _wdb = new DatabaseSync(dbp);
    _wdb.exec('PRAGMA busy_timeout=5000');
  }
  return _wdb;
}
function adminSourceSlug(id) {
  try {
    const r = adminWriteDb().prepare('SELECT slug FROM sources WHERE id=?').get(+id);
    return r ? r.slug : null;
  } catch { return null; }
}
function adminRunPython(args, timeoutMs) {
  return new Promise((resolve, reject) => {
    const { execFile } = require('child_process');
    const py = path.join(process.env.HOME || os.homedir(), 'news-project', 'venv', 'bin', 'python');
    execFile(py, args, { cwd: path.join(process.env.HOME || os.homedir(), 'news-project'), timeout: timeoutMs },
      (err, so) => {
        if (err && !so) return reject(err);
        try { resolve(JSON.parse(String(so).trim().split('\n').pop())); }
        catch { resolve(String(so).slice(0, 400)); }
      });
  });
}

// ---------- REST 路由 ----------
async function handleApi(req, res, url, ip) {
  const q = url.searchParams;
  const p = url.pathname.replace(/^\/api/, '');
  const ok = (obj) => send(res, 200, obj);
  if (p === '/health') return ok({ ...newsdb.health(), time: new Date().toISOString() });
  if (p === '/status') return ok({ ...newsdb.health(), disk: newsdb.diskStatus(),
    mcp: { enabled: !!mcpHandler, endpoint: '/mcp', auth: 'bearer', tools: mcpHandler ? MCP_TOOL_NAMES : [] },
    web_search: websearch.searchConfigured(), time: new Date().toISOString() });
  if (p === '/news/search') return ok(newsdb.searchArticles({   // /api/news 的显式别名
    q: q.get('q'), hours: q.get('hours'), category: q.get('category'), source: q.get('source'),
    language: q.get('language'), sort: q.get('sort'), limit: q.get('limit'), offset: q.get('offset') }));
  if (p === '/news') return ok(newsdb.searchArticles({
    q: q.get('q'), hours: q.get('hours'), category: q.get('category'), source: q.get('source'),
    language: q.get('language'), sort: q.get('sort'), limit: q.get('limit'), offset: q.get('offset') }));
  if (p === '/news/latest') return ok(newsdb.latestArticles({
    hours: q.get('hours'), category: q.get('category'), limit: q.get('limit'),
    offset: q.get('offset'), includePurged: q.get('include_purged') === '1' }));
  let m;
  if ((m = p.match(/^\/news\/(\d+)$/))) {
    const a = newsdb.getArticle(+m[1]);
    return a ? ok(a) : send(res, 404, { error: 'not found' });
  }
  if (p === '/stories/search') return ok(newsdb.searchStories({  // /api/stories 显式别名
    q: q.get('q'), hours: q.get('hours'), category: q.get('category'),
    limit: q.get('limit'), offset: q.get('offset') }));
  if (p === '/stories') return ok(newsdb.searchStories({
    q: q.get('q'), hours: q.get('hours'), category: q.get('category'),
    limit: q.get('limit'), offset: q.get('offset') }));
  if ((m = p.match(/^\/stories\/(\d+)$/))) {
    const st = newsdb.getStory(+m[1]);
    return st ? ok(st) : send(res, 404, { error: 'not found' });
  }
  if (p === '/trending') return ok({ hours: +(q.get('hours') || 24), category: q.get('category') || null,
    results: newsdb.trending({ hours: q.get('hours'), category: q.get('category'), limit: q.get('limit') }) });
  if (p === '/sources') return ok({ results: newsdb.listSources() });
  if (p === '/categories') return ok({ results: newsdb.categories() });
  if (p === '/media') {
    const mq = (q.get('q') || '').trim();
    if (mq) return ok(newsdb.searchArticles({ q: mq, category: 'video', hours: q.get('hours') || 720,
      limit: q.get('limit') || 12, offset: q.get('offset') }));
    return ok(newsdb.latestArticles({
      hours: q.get('hours') || 720, category: 'video', limit: q.get('limit'), offset: q.get('offset') }));
  }
  if (p === '/search') {
    if (rateLimited('api', ip)) { send(res, 429, { error: 'rate limited' }); done(429); return; }
    const r = await querysvc.search(q.get('q') || '', {
      scope: q.get('scope'), time_range: q.get('time_range'), language: q.get('language'),
      region: q.get('region'), category: q.get('category'), limit: q.get('limit'),
      offset: q.get('offset'), hours: q.get('hours'), sort: q.get('sort'), page: q.get('page') });
    return ok(r);
  }
  if ((m = p.match(/^\/images\/(\d+)$/))) return serveImage(res, +m[1]);
  return send(res, 404, { error: 'unknown endpoint', hint: '/api/health /api/news /api/stories /api/trending' });
}

// ---------- MCP (Phase 5): 仅当 SDK 可用且 token 已配置时启用 ----------
let mcpHandler = null;
async function initMcp() {
  if (!MCP_TOKEN) { console.log('[mcp] MCP_TOKEN 未配置 — /mcp 关闭'); return; }
  try {
    const { McpServer } = await import('@modelcontextprotocol/sdk/server/mcp.js');
    const { StreamableHTTPServerTransport } = await import('@modelcontextprotocol/sdk/server/streamableHttp.js');
    const { z } = await import('zod');
    const lib = newsdb;
    mcpHandler = async (req, res, parsedBody) => {
      // 每请求一个无状态 server+transport（官方无状态模式）
      const server = new McpServer({ name: 'serve00-global-hotspots', version: '1.0.0' },
        { capabilities: { tools: {} } });
      const tool = (name, desc, schema, fn) => server.tool(name, desc, schema, async (args) => {
        try { return { content: [{ type: 'text', text: JSON.stringify(await fn(args), null, 1) }] }; }
        catch (e) { return { content: [{ type: 'text', text: 'error: ' + e.message }], isError: true }; }
      });
      tool('search_news', 'Search collected news articles. Filters: q, hours(1-720), category(general|tech|finance|geopolitics|society|video), source slug, language, sort(relevance|recent). Paginated.',
        { q: z.string().optional(), hours: z.number().optional(), category: z.string().optional(),
          source: z.string().optional(), language: z.string().optional(),
          sort: z.enum(['relevance', 'recent']).optional(), limit: z.number().optional(), offset: z.number().optional() },
        (a) => lib.searchArticles(a));
      tool('search_events', 'Search story clusters (same event from multiple outlets).',
        { q: z.string().optional(), hours: z.number().optional(), category: z.string().optional(),
          limit: z.number().optional(), offset: z.number().optional() },
        (a) => lib.searchStories(a));
      tool('get_event', 'Get one story/event with all its articles and timeline.', { id: z.number() },
        (a) => lib.getStory(a.id) || { error: 'not found' });
      tool('get_article', 'Get one article with full text (72h window) and images.', { id: z.number() },
        (a) => lib.getArticle(a.id) || { error: 'not found' });
      tool('get_trending', 'Current trending stories ranked by heat (distinct-source decay formula).',
        { hours: z.number().optional(), category: z.string().optional(), limit: z.number().optional() },
        (a) => ({ results: lib.trending(a || {}) }));
      tool('search_media', 'Search video/media hotspots (YouTube/Bilibili metadata only).',
        { q: z.string().optional(), hours: z.number().optional(), limit: z.number().optional() },
        (a) => lib.searchArticles({ ...a, category: 'video' }));
      tool('get_timeline', 'Event timeline (chronological articles of one story).', { id: z.number() },
        (a) => { const st = lib.getStory(a.id); return st ? st.timeline : { error: 'not found' }; });
      tool('list_sources', 'List all registered sources with health.',
        {}, () => ({ results: lib.listSources() }));
      tool('web_search', 'Search the live internet (not our database). Keyless providers with optional self-hosted SearXNG primary. Args: q (required), time_range (day|week|month|year), language, region, category (general|news), limit, page. Returns title/url/snippet/source/published + per-provider status.',
        { q: z.string(), time_range: z.enum(['day','week','month','year']).optional(),
          language: z.string().optional(), region: z.string().optional(),
          category: z.enum(['general','news']).optional(), limit: z.number().optional(), page: z.number().optional() },
        async (a) => websearch.webSearch(a.q, a));
      tool('read_url', 'Read one web page and extract title/author/published/content/images. Uses the pipeline extraction stack (trafilatura->Scrapling). Never bypasses access controls; returns status ok|inaccessible|needs_js|failed.',
        { url: z.string(), timeout_ms: z.number().optional() },
        async (a) => reader.readUrl(a.url, Math.min(a.timeout_ms || 25000, 45000)));
      tool('search_intelligence', 'Search our collected Global Intelligence database (articles + story clusters combined). Args: q (required), hours, category, language, sort, limit, offset.',
        { q: z.string(), hours: z.number().optional(), category: z.string().optional(),
          language: z.string().optional(), sort: z.enum(['relevance','recent']).optional(),
          limit: z.number().optional(), offset: z.number().optional() },
        (a) => { const arts = lib.searchArticles(a); const sts = lib.searchStories({ q: a.q, hours: a.hours, category: a.category, limit: 5 });
                 return { articles: arts, stories: { total: sts.total, results: sts.results } }; });
      tool('deep_search', 'Multi-step research (no AI needed): web_search -> dedup -> read top pages (multi-source cross-check) -> match against intelligence DB. Args: q (required), time_range, language, category, max_pages (default 3), budget_ms (default 40000).',
        { q: z.string(), time_range: z.enum(['day','week','month','year']).optional(),
          language: z.string().optional(), category: z.string().optional(),
          max_pages: z.number().optional(), budget_ms: z.number().optional() },
        async (a) => querysvc.deepSearch(a.q, a, reader));

      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined,      // 无状态（主流客户端兼容）
        enableJsonResponse: true,           // 能 JSON 就不开 SSE 流（省内存/防耗尽）
        allowedHosts: ['<你的域名>'],
        allowedOrigins: [SITE_ORIGIN],
      });
      await server.connect(transport);
      await transport.handleRequest(req, res, parsedBody);
    };
    console.log('[mcp] ready (stateless, JSON mode, bearer required)');
  } catch (e) {
    console.log('[mcp] init failed:', e.message);
  }
}

function bearerOk(req) {
  const h = req.headers.authorization || '';
  if (!h.startsWith('Bearer ')) return false;
  const token = h.slice(7);
  if (MCP_TOKEN && token === MCP_TOKEN) return true;      // bootstrap env token
  try { return auth.checkMcpBearer(token); } catch { return false; }
}

const server = http.createServer(async (req, res) => {
  const t0 = Date.now();
  const ip = (req.socket.remoteAddress || '').replace('::ffff:', '');
  let url;
  try { url = new URL(req.url, SITE_ORIGIN); } catch { res.writeHead(400); return res.end(); }
  const done = (code) => logLine({ t: new Date().toISOString(), ip, m: req.method,
    p: url.pathname, code, ms: Date.now() - t0 });
  try {
    if (url.pathname === '/mcp') {
      if (!bearerOk(req)) {
        res.writeHead(401, { 'WWW-Authenticate': 'Bearer realm="mcp"', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify({ error: 'unauthorized' }));
        done(401); return;
      }
      if (req.headers.origin && req.headers.origin !== SITE_ORIGIN) {
        send(res, 403, { error: 'origin rejected' }); done(403); return;
      }
      if (rateLimited('mcp', ip)) { send(res, 429, { error: 'rate limited' }); done(429); return; }
      let parsedBody;
      if (req.method === 'POST') {
        const chunks = []; let size = 0;
        for await (const c of req) { size += c.length; if (size > 256 * 1024) { send(res, 413, { error: 'body too large' }); done(413); return; } chunks.push(c); }
        try { parsedBody = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
        catch { send(res, 400, { error: 'invalid json' }); done(400); return; }
      }
      if (!mcpHandler) { send(res, 503, { error: 'mcp unavailable' }); done(503); return; }
      await mcpHandler(req, res, parsedBody);
      done(res.statusCode);
      return;
    }
    // ---- 认证 API（公开）----
    if (url.pathname === '/api/auth/login') {
      const chunks = []; for await (const c of req) chunks.push(c);
      let body = {};
      try { body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); } catch { /* */ }
      const r = auth.login(body.username, body.password, ip);
      if (r.ok) {
        res.setHeader('Set-Cookie', `gi_session=${r.sid}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=604800`);
        send(res, 200, { ok: true, user: r.user, csrf: r.csrf });
      } else send(res, 401, { error: r.error });
      done(res.statusCode); return;
    }
    if (url.pathname === '/api/auth/logout') {
      const m = (req.headers.cookie || '').match(/gi_session=([\w-]+)/);
      if (m) auth.logout(m[1]);
      res.setHeader('Set-Cookie', 'gi_session=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0');
      send(res, 200, { ok: true }); done(200); return;
    }
    const sess = auth.getSession((req.headers.cookie || '').match(/gi_session=([\w-]+)/)?.[1]);
    if (url.pathname === '/api/auth/me') {
      send(res, 200, sess ? { user: { username: sess.username, role: sess.role }, csrf: sess.csrf }
                          : { user: null });
      done(200); return;
    }
    // ---- 管理 API（必须 admin 会话 + 变更需 CSRF 头）----
    if (url.pathname.startsWith('/api/admin/')) {
      if (!sess || sess.role !== 'admin') { send(res, 403, { error: '需要管理员登录' }); done(403); return; }
      if (req.method !== 'GET' && req.headers['x-gi-csrf'] !== sess.csrf) {
        send(res, 403, { error: 'CSRF 校验失败' }); done(403); return;
      }
      if (rateLimited('api', ip)) { send(res, 429, { error: 'rate limited' }); done(429); return; }
      await handleAdmin(req, res, url, sess);
      done(res.statusCode); return;
    }
    if (url.pathname.startsWith('/api/')) {
      if (rateLimited('api', ip)) { send(res, 429, { error: 'rate limited' }); done(429); return; }
      await handleApi(req, res, url, ip);
      done(res.statusCode);
      return;
    }
    if (req.method === 'GET') {
      const file = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
      serveStatic(res, file);
      done(200);
      return;
    }
    send(res, 405, { error: 'method not allowed' }); done(405);
  } catch (e) {
    console.error('[web] error', e.message);
    if (!res.headersSent) send(res, 500, { error: 'internal' });
    done(500);
  }
});

(async () => {
  try {
    const b = auth.ensureBootstrapAdmin();
    auth.pruneSessions();
    if (b.created) {
      const credPath = path.join(process.env.HOME || os.homedir(), 'news-project', 'admin-credentials.txt');
      fs.writeFileSync(credPath, `Global Intelligence 管理员（首次生成，请尽快登录修改）\n用户名: admin\n密码: ${b.password}\n生成: ${new Date().toISOString()}\n`, { mode: 0o600 });
      console.log('[auth] bootstrap admin created; credentials at ~/news-project/admin-credentials.txt (600)');
    }
  } catch (e) { console.log('[auth] bootstrap skipped:', e.message); }
  await initMcp();
  server.listen(PORT, () => console.log(`[web] listening on ${PORT} (pid ${process.pid})`));
})();

process.on('uncaughtException', (e) => console.error('[web] uncaught', e.message));
process.on('unhandledRejection', (e) => console.error('[web] unhandled', String(e).slice(0, 200)));
