// lib/reader.js — URL Reader（Python 一次性子进程, 复用管道 venv 的 trafilatura/Scrapling 栈）
// 并发守卫: 最多 2 个同时子进程（保护 20 进程预算）; 25s 硬超时; Crawl4AI 不默认。
'use strict';
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');

const HOME = process.env.HOME || os.homedir();
const PY = path.join(HOME, 'news-project', 'venv', 'bin', 'python');
const CWD = path.join(HOME, 'news-project');
let running = 0;
const queue = [];

function exec(url, timeoutMs, maxChars) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; running--; resolve(v); } };
    running++;
    const p = spawn(PY, ['-m', 'news.reader', url, `--timeout=${Math.round(timeoutMs / 1000) - 4}`, `--max-chars=${maxChars || 12000}`],
      { cwd: CWD, timeout: timeoutMs, killSignal: 'SIGKILL' });
    let buf = '';
    p.stdout.on('data', (c) => { buf += c; });
    p.stderr.on('data', () => { /* 忽略警告 */ });
    p.on('error', (e) => finish({ url, status: 'failed', error: 'spawn: ' + e.message }));
    p.on('close', () => {
      const i = buf.lastIndexOf('{');
      try { finish(JSON.parse(buf.slice(i < 0 ? 0 : i).trim())); }
      catch { finish({ url, status: 'failed', error: 'reader subprocess produced no JSON (timeout or crash)' }); }
    });
  });
}

function readUrl(url, timeoutMs = 25000, maxChars = 12000) {
  if (!/^https?:\/\//.test(url)) return Promise.resolve({ url, status: 'failed', error: 'invalid url' });
  maxChars = Math.max(200, Math.min(+maxChars || 12000, 40000));   // absolute 上限
  if (running >= 2) return new Promise((res) => queue.push(() => exec(url, timeoutMs, maxChars).then(res)));
  return exec(url, timeoutMs, maxChars);
}

module.exports = { readUrl };
