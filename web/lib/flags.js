// lib/flags.js — [R11-P3] 功能开关(后台可视化)。文件持久化, 删除文件=回安全默认=自带回滚。
'use strict';
const fs = require('fs'), path = require('path'), os = require('os');
// [R11] __dirname 解析(public_nodejs→上3级=用户根), worker 的 HOME 环境不可靠
const HOME = (process.env.HOME && fs.existsSync(path.join(process.env.HOME, 'news-project'))) ? process.env.HOME : path.join(__dirname, '..', '..', '..');
const FILE = path.join(HOME, 'news-project', 'news-data', 'state', 'feature-flags.json');
const DEFAULTS = { public_rest: true, web_search_api: false, ui_gate: true, api_rpm_global: 120, mcp_rpm: 60 };
// [R12-A] 每端点开关 + 每 IP 端点限流(次/分, 0/缺省=用全局 api 限流)
const API_ENDPOINTS = ['news','news_latest','news_item','stories','stories_search','trending','sources','media','images','search','status','categories'];
const API_DEFAULTS = Object.assign({ public_rest: true, web_search_api: false, ui_gate: true },
  { api_endpoints: Object.fromEntries(API_ENDPOINTS.map(e => [e, true])), api_rpm: { news: 30, trending: 40, stories: 60, search: 10 } });
DEFAULTS.api_endpoints = API_DEFAULTS.api_endpoints;
DEFAULTS.api_rpm = API_DEFAULTS.api_rpm;
let cache = { at: 0, v: Object.assign({}, DEFAULTS) };
function flags() {
  if (Date.now() - cache.at < 3000) return cache.v;
  try { cache.v = Object.assign({}, DEFAULTS, JSON.parse(fs.readFileSync(FILE, 'utf8'))); }
  catch { cache.v = Object.assign({}, DEFAULTS); }
  cache.at = Date.now();
  return cache.v;
}
function fresh(){try{const v=Object.assign({},DEFAULTS,JSON.parse(fs.readFileSync(FILE,'utf8')));cache.v=v;cache.at=Date.now();return v}catch{cache.v=Object.assign({},DEFAULTS);cache.at=Date.now();return cache.v}}
module.exports = { flags, fresh, FILE, DEFAULTS };
