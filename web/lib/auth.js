// lib/auth.js — 认证/会话/MCP Token 管理（独立 auth.db; 不触碰管道 news.db）
// 密码: crypto.scrypt(N=16384) + 随机盐, 只存哈希。会话: DB 持久化 + HttpOnly Cookie。
// MCP Token: 只存 sha256 哈希 + 前 8 位前缀; 全文仅创建时返回一次。
'use strict';
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { DatabaseSync } = require('node:sqlite');

const HOME = process.env.HOME || os.homedir();
const DATA = path.join(HOME, 'news-project', 'news-data');
const AUTH_DB = path.join(DATA, 'database', 'auth.db');

let _db = null;
function db() {
  if (!_db) {
    _db = new DatabaseSync(AUTH_DB);
    _db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000');
    _db.exec(`CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, pass_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'user', enabled INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, last_login_at TEXT);
      CREATE TABLE IF NOT EXISTS sessions(
      id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL,
      created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS mcp_tokens(
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
      token_prefix TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, revoked_at TEXT,
      created_at TEXT NOT NULL, last_used_at TEXT, call_count INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS mcp_scopes_migrated(migrated INTEGER)
      CREATE TABLE IF NOT EXISTS audit_log(
      id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT, action TEXT, detail TEXT)`);
  }
  // [R12-B] token 分权迁移(幂等): scopes 默认 '*' = 全部工具; 回滚: ALTER TABLE mcp_tokens DROP COLUMN scopes
  try { _db.exec("ALTER TABLE mcp_tokens ADD COLUMN scopes TEXT NOT NULL DEFAULT '*'"); }
  catch (e) { if (!String(e.message).includes('duplicate column')) throw e; }
  return _db;
}

function nowIso(offsetH = 0) {
  return new Date(Date.now() + offsetH * 3600e3).toISOString().replace(/\.\d+Z$/, 'Z');
}

// ---------- 密码 ----------
function hashPassword(pw) {
  const salt = crypto.randomBytes(16);
  const N = 16384, r = 8, p = 1;
  const h = crypto.scryptSync(pw, salt, 32, { N, r, p });
  return `scrypt$${N}$${r}$${p}$${salt.toString('hex')}$${h.toString('hex')}`;
}
function verifyPassword(pw, stored) {
  try {
    const [alg, N, r, p, saltH, hashH] = String(stored).split('$');
    if (alg !== 'scrypt') return false;
    const h = crypto.scryptSync(pw, Buffer.from(saltH, 'hex'), 32, { N: +N, r: +r, p: +p });
    return crypto.timingSafeEqual(h, Buffer.from(hashH, 'hex'));
  } catch { return false; }
}

// ---------- 用户 ----------
function ensureBootstrapAdmin() {
  const d = db();
  const n = d.prepare('SELECT COUNT(*) AS n FROM users').get().n;
  if (n > 0) return { created: false };
  const pw = crypto.randomBytes(18).toString('base64url');
  d.prepare('INSERT INTO users(username,pass_hash,role,enabled,created_at) VALUES(?,?,?,1,?)')
    .run('admin', hashPassword(pw), 'admin', nowIso());
  audit('system', 'bootstrap-admin', 'created initial admin user');
  return { created: true, username: 'admin', password: pw };
}

function createUser(username, password, role) {
  if (!/^[a-zA-Z0-9_-]{2,32}$/.test(username)) return { error: '用户名仅允许 2-32 位字母/数字/_/-' };
  if (String(password).length < 8) return { error: '密码至少 8 位' };
  if (!['admin', 'user'].includes(role)) return { error: 'role 无效' };
  try {
    db().prepare('INSERT INTO users(username,pass_hash,role,enabled,created_at) VALUES(?,?,?,1,?)')
      .run(username, hashPassword(password), role, nowIso());
    audit('admin', 'user-create', username);
    return { ok: true };
  } catch (e) {
    return { error: String(e.message).includes('UNIQUE') ? '用户名已存在' : e.message };
  }
}

function listUsers() {
  return db().prepare('SELECT id, username, role, enabled, created_at, last_login_at FROM users ORDER BY id').all();
}

function setUserEnabled(id, enabled) {
  const u = db().prepare('SELECT username FROM users WHERE id=?').get(+id);
  if (!u) return { error: 'user not found' };
  if (u.username === 'admin' && !enabled) return { error: '不能禁用 bootstrap 管理员' };
  db().prepare('UPDATE users SET enabled=? WHERE id=?').run(enabled ? 1 : 0, +id);
  if (!enabled) db().prepare('DELETE FROM sessions WHERE user_id=?').run(+id);
  audit('admin', enabled ? 'user-enable' : 'user-disable', u.username);
  return { ok: true };
}

function resetUserPassword(id, password) {
  if (String(password).length < 8) return { error: '密码至少 8 位' };
  const u = db().prepare('SELECT username FROM users WHERE id=?').get(+id);
  if (!u) return { error: 'user not found' };
  db().prepare('UPDATE users SET pass_hash=? WHERE id=?').run(hashPassword(password), +id);
  db().prepare('DELETE FROM sessions WHERE user_id=?').run(+id);
  audit('admin', 'user-reset-password', u.username);
  return { ok: true };
}

// ---------- 登录/会话 ----------
const loginFails = new Map();   // ip → {n, until}
function loginRateLimited(ip) {
  const r = loginFails.get(ip);
  if (r && r.until > Date.now() && r.n >= 5) return true;
  return false;
}
function recordLoginFail(ip) {
  const r = loginFails.get(ip) || { n: 0, until: 0 };
  r.n += 1;
  if (r.n >= 5) r.until = Date.now() + 15 * 60e3;
  loginFails.set(ip, r);
}
function clearLoginFails(ip) { loginFails.delete(ip); }

function login(username, password, ip) {
  if (loginRateLimited(ip)) return { error: '登录失败次数过多，请 15 分钟后重试' };
  const u = db().prepare('SELECT * FROM users WHERE username=?').get(String(username || ''));
  if (!u || !u.enabled || !verifyPassword(password, u.pass_hash)) {
    recordLoginFail(ip);
    audit('anon', 'login-fail', String(username).slice(0, 32));
    return { error: '用户名或密码错误' };
  }
  clearLoginFails(ip);
  const sid = crypto.randomBytes(24).toString('base64url');
  const csrf = crypto.randomBytes(16).toString('base64url');
  db().prepare('INSERT INTO sessions(id,user_id,csrf,created_at,expires_at) VALUES(?,?,?,?,?)')
    .run(sid, u.id, csrf, nowIso(), nowIso(24 * 7));
  db().prepare('UPDATE users SET last_login_at=? WHERE id=?').run(nowIso(), u.id);
  audit(u.username, 'login', '');
  return { ok: true, sid, csrf, user: { username: u.username, role: u.role } };
}

function getSession(sid) {
  if (!sid || sid.length > 64) return null;
  const s = db().prepare('SELECT s.*, u.username, u.role, u.enabled FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=?').get(sid);
  if (!s || !s.enabled) return null;
  if (s.expires_at < nowIso()) { db().prepare('DELETE FROM sessions WHERE id=?').run(sid); return null; }
  return s;
}

function logout(sid) {
  db().prepare('DELETE FROM sessions WHERE id=?').run(sid || '');
  audit('session', 'logout', '');
  return { ok: true };
}

// 清理过期会话（每次登录时顺手）
function pruneSessions() {
  try { db().prepare('DELETE FROM sessions WHERE expires_at < ?').run(nowIso()); } catch { /* */ }
}

// ---------- MCP Token ----------
function sha256(s) { return crypto.createHash('sha256').update(s).digest('hex'); }

function setMcpTokenScopes(id, scopes) {
  let sc = String(scopes || '*').trim() || '*';
  if (sc !== '*' && !/^[a-z_]+(,[a-z_]+)*$/.test(sc)) return { error: 'scopes 格式: * 或 tool1,tool2' };
  const t = db().prepare('SELECT id, name FROM mcp_tokens WHERE id=?').get(+id);
  if (!t) return { error: 'token 不存在' };
  db().prepare('UPDATE mcp_tokens SET scopes=? WHERE id=?').run(sc, +id);
  audit('admin', 'mcp-token-scopes', t.name + ' → ' + sc);
  return { ok: true, id: +id, scopes: sc };
}

function createMcpToken(name, scopes) {
  name = String(name || '').trim().slice(0, 40) || 'unnamed';
  const token = 'gi_' + crypto.randomBytes(24).toString('base64url');
  const prefix = token.slice(0, 11);
  try {
    let sc = String(scopes || '*').trim() || '*';
    if (!/^\*(,[a-z_]+)*(\/)?$/.test(sc) && !/^[a-z_]+(,[a-z_]+)*$/.test(sc)) return { error: 'scopes 格式: * 或 tool1,tool2' };
    db().prepare('INSERT INTO mcp_tokens(name,token_hash,token_prefix,scopes,enabled,created_at) VALUES(?,?,?,?,1,?)')
      .run(name, sha256(token), prefix, sc, nowIso());
    audit('admin', 'mcp-token-create', name);
    return { ok: true, token, prefix, note: '完整 Token 仅本次显示，数据库只存哈希' };
  } catch (e) { return { error: e.message }; }
}

function listMcpTokens() {
  return db().prepare(`SELECT id, name, token_prefix, scopes, enabled, revoked_at IS NOT NULL AS revoked,
    created_at, last_used_at, call_count FROM mcp_tokens ORDER BY id DESC`).all();
}

function mcpTokenAction(id, action) {
  const t = db().prepare('SELECT * FROM mcp_tokens WHERE id=?').get(+id);
  if (!t) return { error: 'token not found' };
  if (action === 'revoke') {
    db().prepare('UPDATE mcp_tokens SET enabled=0, revoked_at=? WHERE id=?').run(nowIso(), +id);
    audit('admin', 'mcp-token-revoke', t.name);
    return { ok: true };
  }
  if (action === 'enable') {
    db().prepare('UPDATE mcp_tokens SET enabled=1, revoked_at=NULL WHERE id=?').run(+id);
    audit('admin', 'mcp-token-enable', t.name);
    return { ok: true };
  }
  if (action === 'delete') {
    db().prepare('DELETE FROM mcp_tokens WHERE id=?').run(+id);
    audit('admin', 'mcp-token-delete', t.name);
    return { ok: true };
  }
  return { error: 'unknown action' };
}

// MCP Bearer 校验: 先查 DB token（启用未撤销）, 再查 env bootstrap token
function resolveMcpBearer(bearer) {
  if (!bearer) return null;
  const t = db().prepare('SELECT id, scopes FROM mcp_tokens WHERE token_hash=? AND enabled=1 AND revoked_at IS NULL').get(sha256(bearer));
  if (t) {
    db().prepare('UPDATE mcp_tokens SET last_used_at=?, call_count=call_count+1 WHERE id=?').run(nowIso(), t.id);
    return { id: t.id, scopes: t.scopes || '*' };
  }
  return null;
}
function checkMcpBearer(bearer) { return !!resolveMcpBearer(bearer); }

function audit(actor, action, detail) {
  try {
    db().prepare('INSERT INTO audit_log(at,actor,action,detail) VALUES(?,?,?,?)')
      .run(nowIso(), String(actor).slice(0, 32), String(action).slice(0, 40), String(detail).slice(0, 200));
  } catch { /* 审计失败不阻塞主流程 */ }
}
function tailAudit(n = 50) {
  return db().prepare('SELECT at, actor, action, detail FROM audit_log ORDER BY id DESC LIMIT ?').all(+n || 50);
}

module.exports = { db, AUTH_DB, ensureBootstrapAdmin, createUser, listUsers, setUserEnabled,
  resetUserPassword, login, getSession, logout, pruneSessions, createMcpToken, listMcpTokens,
  resolveMcpBearer, setMcpTokenScopes,
  mcpTokenAction, checkMcpBearer, audit, tailAudit, verifyPassword, hashPassword };
