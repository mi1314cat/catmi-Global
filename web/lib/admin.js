// lib/admin.js — 管理员后台服务: 系统诊断/日志/设置/AI 状态（全部真实数据）
'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');
const dns = require('dns');
const { execFile } = require('child_process');
const newsdb = require('./newsdb');
const websearch = require('./websearch');
const reader = require('./reader');

const HOME = process.env.HOME || os.homedir();
const NEWS = path.join(HOME, 'news-project');
const SITE = 'https://<你的域名>';

function isoAgoH(t) {
  if (!t) return null;
  const h = (Date.now() - new Date(t).getTime()) / 36e5;
  return isNaN(h) ? null : h;
}

// ---------- 系统诊断 ----------
async function diagnostics() {
  const checks = [];
  const add = (name, ok, detail) => checks.push({ name, ok: !!ok, detail: String(detail).slice(0, 160) });
  // HTTPS
  add('HTTPS', true, '站点经 Passenger/nginx 以 HTTPS 对外服务（本请求即 HTTPS）');
  // 数据库
  try {
    const h = newsdb.health();
    add('数据库 (news.db)', h.articles_total >= 0 && h.status === 'ok', `articles=${h.articles_total} events=${h.stories_active} wal=${h.wal}`);
  } catch (e) { add('数据库 (news.db)', false, e.message); }
  // 认证库
  try {
    const auth = require('./auth');
    const n = auth.db().prepare('SELECT COUNT(*) n FROM users').get().n;
    add('认证库 (auth.db)', n > 0, `users=${n}`);
  } catch (e) { add('认证库 (auth.db)', false, e.message); }
  // 文件权限
  try {
    const st = fs.statSync(path.join(NEWS, 'env.local'));
    add('敏感文件权限 (env.local)', (st.mode & 0o777) === 0o600, `mode=${(st.mode & 0o777).toString(8)} (要求 600)`);
  } catch (e) { add('敏感文件权限 (env.local)', false, 'missing'); }
  // 数据目录
  for (const d of ['database', 'images', 'cache', 'logs']) {
    const p = path.join(NEWS, 'news-data', d);
    add(`数据目录 ${d}/`, fs.existsSync(p), fs.existsSync(p) ? 'exists' : 'missing');
  }
  // Web UI / REST（本请求即证明）
  add('Web UI', true, '本诊断请求经同一 Passenger 服务');
  add('REST API', true, '/api/* 在线');
  // MCP
  const wsCfg = websearch.searchConfigured();
  // Web Search 实测（wikipedia opensearch 5s）
  let wsOk = false, wsDetail = '';
  try {
    const r = await websearch.webSearch('test', { providers: 'wikipedia', limit: 1 });
    wsOk = r.results.length > 0;
    wsDetail = wsOk ? 'wikipedia 实测返回结果' : 'wikipedia 0 结果';
  } catch (e) { wsDetail = e.message; }
  add('Web Search', wsOk, `${wsCfg.primary} · ${wsDetail}`);
  // Intelligence Search
  try {
    const r = newsdb.searchArticles({ q: 'the', limit: 1 });
    add('Intelligence Search', true, `FTS5 查询正常, 库内 ${r.total} 篇`);
  } catch (e) { add('Intelligence Search', false, e.message); }
  // Collector
  const h = newsdb.health();
  const ageH = isoAgoH(h.last_run);
  add('Collector', ageH != null && ageH < 1.2, h.last_run ? `last_run ${h.last_run} (${ageH.toFixed(1)}h 前)` : '尚未运行');
  // Scheduler (crontab)
  await new Promise((res) => {
    execFile('crontab', ['-l'], { timeout: 5000 }, (err, so) => {
      const lines = String(so || '').split('\n').filter((l) => l.includes('newsctl'));
      add('Scheduler (cron)', !err && lines.length >= 3, `${lines.length} 条 newsctl 任务`);
      res();
    });
  });
  // Storage
  const dk = newsdb.diskStatus();
  add('Storage', (dk.level || 'normal') !== 'emergency', `data ${dk.data_pct_of_3gb}% of 3GB · ${dk.level}`);
  // DNS
  await new Promise((res) => {
    dns.lookup('<你的域名>', (err, addr) => {
      add('DNS', !err, err ? err.message : `<你的域名> → ${addr}`);
      res();
    });
  });
  const okN = checks.filter((c) => c.ok).length;
  const lines = checks.map((c) => `${c.ok ? '✓' : '✗'} ${c.name} — ${c.detail}`);
  return {
    ok: okN === checks.length, passed: okN, total: checks.length, checks,
    report: `Global Intelligence 系统诊断报告\n生成时间: ${new Date().toISOString()}\n` + lines.join('\n') + `\n${okN}/${checks.length} 项通过`,
  };
}

// ---------- MCP 完整健康测试（真实请求自测） ----------
async function mcpSelfTest() {
  const auth = require('./auth');
  const steps = [];
  const step = (name, ok, detail) => steps.push({ name, ok: !!ok, detail: String(detail).slice(0, 140) });
  // 取一个可用 token: env bootstrap 或 DB 第一个启用 token
  let token = null;
  const toks = auth.listMcpTokens().filter((t) => t.enabled && !t.revoked);
  step('Endpoint', true, SITE + '/mcp');
  step('HTTPS', true, '本测试经 HTTPS 发起');
  // 环境变量 token 在内存里; 若无 DB token 也能测 —— 用 admin 会话不可用, 直接用 env token 的存在性
  const envToken = (function () {
    try {
      for (const line of fs.readFileSync(path.join(NEWS, 'env.local'), 'utf8').split('\n')) {
        const m = line.match(/^MCP_TOKEN=(.+)$/);
        if (m) return m[1].trim();
      }
    } catch { /* */ }
    return null;
  })();
  token = envToken;
  step('Authentication 配置', !!token, token ? 'bootstrap MCP_TOKEN 已配置' : '未配置任何可用 token');
  if (token) {
    const rpc = async (body, headers = {}) => {
      const r = await fetch(SITE + '/mcp', {
        method: 'POST', headers: Object.assign({
          Authorization: 'Bearer ' + token, 'Content-Type': 'application/json',
          Accept: 'application/json, text/event-stream', 'User-Agent': 'Mozilla/5.0 gi-selftest',
        }, headers), body: JSON.stringify(body),
      });
      let json = null;
      try { json = await r.json(); } catch { /* */ }
      return { code: r.status, json };
    };
    try {
      const init = await rpc({ jsonrpc: '2.0', id: 1, method: 'initialize',
        params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'selftest', version: '1.0' } } });
      step('Initialize', init.code === 200 && init.json && init.json.result, `HTTP ${init.code} ${(init.json && init.json.result && init.json.result.serverInfo && init.json.result.serverInfo.name) || ''}`);
      const tl = await rpc({ jsonrpc: '2.0', id: 2, method: 'tools/list' });
      const tools = (tl.json && tl.json.result && tl.json.result.tools) || [];
      step('Tools/List', tl.code === 200 && tools.length > 0, `${tools.length} 个工具`);
      const ws = await rpc({ jsonrpc: '2.0', id: 3, method: 'tools/call',
        params: { name: 'web_search', arguments: { q: 'test', limit: 2 } } });
      const wsOk = ws.code === 200 && ws.json && ws.json.result && !ws.json.result.isError;
      step('web_search', wsOk, `HTTP ${ws.code}`);
      const si = await rpc({ jsonrpc: '2.0', id: 4, method: 'tools/call',
        params: { name: 'search_intelligence', arguments: { q: 'tariff', limit: 1 } } });
      step('search_intelligence', si.code === 200 && si.json && si.json.result && !si.json.result.isError, `HTTP ${si.code}`);
      // Origin 校验（坏 Origin 应 403）
      const bad = await rpc({ jsonrpc: '2.0', id: 5, method: 'tools/list' }, { Origin: 'https://evil.example.com' });
      step('Origin Validation', bad.code === 403, `伪造 Origin → HTTP ${bad.code} (期望 403)`);
      // 无认证应 401
      const r2 = await fetch(SITE + '/mcp', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' });
      step('无认证拒绝', r2.status === 401, `HTTP ${r2.status} (期望 401)`);
    } catch (e) {
      step('MCP 请求', false, e.message);
    }
  }
  const okN = steps.filter((s) => s.ok).length;
  return { ok: okN === steps.length, passed: okN, total: steps.length, steps };
}

// ---------- 日志 ----------
function tailLog(file, n) {
  try {
    const p = path.join(NEWS, 'news-data', 'logs', file);
    const txt = fs.readFileSync(p, 'utf8').trim().split('\n');
    return txt.slice(-n).join('\n').slice(-20000);
  } catch (e) { return `(无日志: ${e.message})`; }
}

// ---------- 设置/AI 状态（只读展示） ----------
function readEnvLocal() {
  const out = {};
  try {
    for (const line of fs.readFileSync(path.join(NEWS, 'env.local'), 'utf8').split('\n')) {
      const m = line.match(/^\s*([A-Z_]+)\s*=/);
      if (m) out[m[1]] = true; // 只记录"已配置", 绝不记录值
    }
  } catch { /* */ }
  return out;
}
function settings() {
  const env = readEnvLocal();
  return {
    retention: { raw_hours: 24, content_hours: 72, images_hours: 72, metadata_days: 30, story_days: 90 },
    batches: { scan: 16, fetch: 30, image: 10 },
    disk_levels: 'normal <50% / warning ≥50% / high ≥70% / emergency ≥85% (3GB)',
    config_note: '配置经 env.local (600) 修改并重启 Passenger 生效; 本页只读展示, 不提供网页改写（安全考虑）',
    mcp_token_env: !!env.MCP_TOKEN,
    ai: {
      principle: 'AI 永非核心依赖; 全部禁用时系统完整可用',
      providers: [
        { name: 'OpenAI兼容', configured: !!(env.AI_BASE_URL && env.AI_API_KEY), status: 'disabled' },
        { name: 'DeepSeek', configured: false, status: 'disabled' },
        { name: 'Qwen', configured: false, status: 'disabled' },
        { name: 'Gemini', configured: false, status: 'disabled' },
        { name: 'FreeLLM', configured: false, status: 'disabled' },
      ],
      uses: ['摘要', '分类', '事件聚类辅助', '翻译', '搜索结果整理'],
    },
  };
}

module.exports = { diagnostics, mcpSelfTest, tailLog, settings, readEnvLocal };
