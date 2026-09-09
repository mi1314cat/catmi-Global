# SEARCH_ARCHITECTURE — Web Search + Intelligence Search 架构（2026-09-09 v1）

> 目标重述: 本系统 = **Agent 的全球互联网搜索 + 长期情报库 + 网页阅读** 基础设施（不是新闻网站）。
> 三个核心能力: ① Web Search（互联网现在有什么）② Intelligence Search（我的库历史有什么）③ URL Reader（读取任一网页）。
> 统一入口: MCP（Agent 主用）/ REST API（通用）/ Web Console（人类观察）——三者共享 `web/lib/query.js`。

## 1. 搜索后端选型结论（Serve00 实测约束下）

| 方案 | 判定 | 理由（实测） |
|---|---|---|
| **A. SearXNG 装在 Serve00** | ❌ 不采用 | SearXNG 是常驻 Web 服务（uWSGI/gunicorn + 推荐 Redis），RAM 150-300MB 级；Serve00 共享主机 512MB 总额 + 仅 Passenger 可绑流量 + 无 Docker + 20 进程上限——强上会挤死情报管道 |
| **B. SearXNG 放外部 VPS** | ✅ **设计为 PRIMARY 插槽**（现在就绪, 未来即插） | `env.local` 加一行 `SEARXNG_URL=https://your-vps/searxng` → web_search 自动切换为主 provider（JSON API, 支持 time_range/language/category/pageno）；未配置时零影响 |
| **C. 自写 Provider 层（当前已上线）** | ✅ **当前运行方案** | 5 个 keyless provider 并发查询 + 逐 provider 状态记录 + 跨源去重 + 独立降级——**零 API Key、零新增依赖、零额外服务器**, 今天就能用 |

**为什么这样选**: 用户核心诉求是"不依赖付费搜索 API + 尽量自托管"。SearXNG 自托管是终极形态但需要 VPS（用户当前没有）；公共 SearXNG 实例对数据中心 IP 不稳定且 JSON 多被关闭——所以把 SearXNG 做成**可插拔 PRIMARY**，同时内置在 Serve00 上已实测可用的 keyless 路线作为现在时。任何一个 provider 失败不影响整体（实测: 同一查询 ddg/bing 偶发被封时 gnews/bingnews/wikipedia 仍返回结果）。

## 2. Provider 清单（web/lib/websearch.js）

| Provider | 状态 | 类型 | 时间过滤 | 语言/地区 | 备注 |
|---|---|---|---|---|---|
| **searxng** | 可插拔 PRIMARY | JSON API | ✅ time_range | ✅ language | SEARXNG_URL 配置即启用 |
| **ddg** (html) | ✅ 实测可用（间歇 bot 限流） | HTML 解析 | ✗ | kl 地区码 | POST 形式, 间歇性 0 结果→自动降级 |
| **bing** (html) | ⚠️ 间歇可用 | HTML 解析 | ✗ | setlang/cc | 数据中心 IP 偶发封禁 |
| **gnews** (rss) | ✅ **最稳** | RSS | ✅ when:1d/7d/1m/1y | ✅ hl/gl/ceid（含中文实测） | 链接为 Google 重定向（read_url 可跟随） |
| **bingnews** (rss) | ✅ 稳定 | RSS | 部分 | setlang | bing url= 链接自动解包 |
| **wikipedia** | ✅ 稳定 | opensearch API | ✗ | ✅ 语言版 | 实体/背景参考 |

每次搜索返回 `providers: [{provider, status: ok|error, latency_ms, count|error}]` —— 降级过程完全可观测。

## 3. 数据流

```
Agent ──MCP──> app.js (Node)
                 ├─ web_search/deep_search ──> lib/query.js ──> lib/websearch.js ──> 5 providers（并发, allSettled）
                 ├─ search_intelligence ─────> lib/newsdb.js ──> SQLite(WAL/FTS5)
                 └─ read_url ────────────────> lib/reader.js ──> spawn venv python -m news.reader ──> trafilatura→Scrapling
REST /api/search ─────────────────────────────> 同一 query.js
Web Console Search 页 ─────────────────────────> 同一 /api/search
```

## 4. 统一接口

```
search(query, scope=web|intelligence|all, time_range=day|week|month|year, language, region, category, limit≤20, page)
```
- REST: `GET /api/search?q=&scope=&time_range=&language=&limit=&offset=`
- MCP: `web_search`（纯 web）/ `search_intelligence`（纯库）/ `deep_search`（编排）

## 5. deep_search（确定性多步研究, 无 AI）

```
web_search(limit 10, 多 provider)
  → 去重 + 每域名保 1 条 → 选 top N(默认3) 来源
  → read_url 逐页读（预算 40s 硬限制, 每页 20s, 最多 2 并发 python 子进程）
  → intelligence 库关联（articles + stories）
  → 返回 {sources_picked, pages[{status,excerpt}], intelligence_matches, steps, elapsed}
```
失败语义: 页面 401/403/429 → `inaccessible`（不绕过）; JS 动态页 → `needs_js`（Crawl4AI 默认关, 留外部渲染钩子）。AI 以后只用于摘要/排序增强, 不在链路上。

## 6. 资源消耗实测（Serve00）

| 项 | 实测 |
|---|---|
| web_search 单次 | 300-720ms（并发 provider）；Node 进程内, 无新进程 |
| read_url 单页 | 2.0s（Guardian 3978 字符）; 子进程寿命 ~2-4s, 并发上限 2 |
| deep_search | 2.3-3s（读 1-3 页 + 库关联）；预算硬顶 40s |
| 新增依赖 | **0**（Node 零框架; Python 复用现有 venv 的 httpx/trafilatura/scrapling） |
| 进程峰值 | Passenger node(常驻 1) + reader 子进程 ≤2 → 总进程仍 <10/20 |

## 7. 已知边界
- ddg/bing HTML 从数据中心 IP 偶发 bot 拦截（表现: 0 结果）→ 降级到 gnews/bingnews（新闻类查询最稳）; 若需要网页类结果更稳 → 配置 SEARXNG_URL 指向自建实例
- gnews 返回的是 Google 重定向链接（Agent 可继续 read_url 跟随到原文）
- time_range 对 ddg/bing 网页版不可用（HTML 无可靠参数）——仅 searxng/gnews/bingnews 支持时间过滤

---

## 8. 外部研究实证（2026-09-09 子代理调查, 全文见 SEARCH_RESEARCH_FULL.md）

| 事实 | 对本系统的影响 |
|---|---|
| SearXNG RAM: 默认 uWSGI ≈600MB(4核), workers=1 ≈150MB; docker 空载 >1.3GB; limiter 需 Valkey, public_instance=true 无 Valkey 直接退出 | **确认不上 Serve00**（512MB 总额）; VPS 方案需 workers=1 + json 开启 |
| JSON API 默认关闭（settings.yml formats 需加 json, 否则 403） | 自建/用实例时必须确认 JSON 开启 |
| searx.space 92 实例中**数据中心 IP 实测仅 2 个 JSON 可用**（search.mectov.my.id, sx.xo.st）, 源码默认 API 限 4 次/h/IP, 列表站成功率失真 | 公共实例只配 fallback tier; 若要用: 设 `SEARXNG_URL=https://search.mectov.my.id`（一行, 我们的 searxng provider 直接吃） |
| **DDG html/lite 对数据中心 IP = duck CAPTCHA（实质死）**; Bing 网页版 200/10×b_algo 软可用 | 我们的 ddg provider 降级为低可信层（实测间歇 ok/封禁, 架构已兼容）; bing html 保留软可用层 |
| Google News RSS（when:1d/after:, 48-100 items）/ Bing News RSS / Wikipedia opensearch 均**稳** | ✅ 与我们实测一致——主力层选型正确 |
| **ddgs**（2,941★ MIT, 10 个 text 后端, 自带 mcp）与 **Argo**（119★, 150+ 引擎）为纯 Python 轻量 meta-search 候选 | 记入下阶段候选: ddgs 可经 Python 子进程接入为额外 provider（需先验证 primp 依赖 FreeBSD 源码构建）; 现有 5 provider 已满足零 key 基线 |
| mcp-searxng（1,214★ MIT, SEARXNG_URL 环境变量约定与本项目一致） | 命名对齐; 若上 VPS 可直接复用其部署形态 |
| AgentSearch（强依赖 CloakBrowser Chromium fork, 2★）排除; Crawl4AI 读单页需 Playwright Chromium 500-700MB/用户, **512MB 不现实**; **Scrapling 默认 Fetcher 同步无浏览器内存最低档** | URL Reader 选型坐实: Scrapling 常规栈 + 无浏览器 + Crawl4AI 永不默认（needs_js 状态预留外部渲染钩子） |

## 9. 结论（研究后不变, 置信度提升）
方案 D（自写 provider 层）= 研究报告对 Serv00 的首选推荐, 且已在生产运行。SearXNG 两级路径: ① 用户 VPS（workers=1 + json）→ PRIMARY; ② 2 个可用公共实例 → 手动 SEARXNG_URL 兜底（4 次/h 限额, 仅当主力层全挂时人工启用）。
