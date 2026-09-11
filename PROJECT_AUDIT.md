# PROJECT_AUDIT (R11 起点审计, 2026-09-10, 基线 aa1b1d6)

## 1. 架构与数据流
cron(Python3.11, venv) → discovery → fetch(批次80, breaker) → reader(trafilatura 子进程) → dedup → 聚类(story/event) → trending。
node22(app.js) = REST(/api/*) + MCP(/mcp, 12工具, Bearer sha256) + Admin(session+CSRF) + 静态UI(公开!)。
DB: news.db(articles/stories/story_articles/sources/crawl_tasks/crawl_errors, 54MB) + auth.db(users/sessions/api_tokens)。flags: 无(现状硬编码)。

## 2. 搜索流程
- 本地: newsdb.searchArticles/searchStories (excerpt 截500, 内存红线)
- 实时: websearch.js 6 provider (searxng未配/ddg POST优先+GET兜底/bing 解包/gnews/bingnews/wikipedia list=search), fetchText 1MB
- deep_search: app.js 内联, 预算 {rounds:2, readUrls:3, 12k chars, 45s}

## 3. /api/search 风险 (审计确认)
无鉴权即可触发真实出网搜索(同一 websearch.js)。限流仅 IP 120/min。**R10 实证: 同 IP 高频→DDG 验证码墙→自伤 MCP web_search**。陌生人滥用 = 白嫖出网 + 伤 IP 信誉。其余 /api/* 为纯 DB 读(便宜)。

## 4. 认证现状
- 已有(复用, 不重写): auth.js scrypt(16384/8/1), sessions 表, HttpOnly+Secure+SameSite=Lax cookie, X-GI-CSRF, MCP api_tokens(仅存 sha256+前缀), /api/auth/login|logout|me, 登录限流
- 缺失: ① 静态 UI 无门(GET / 直接 serveStatic) ② /api/search 无 token ③ 无功能开关(REST 公开性硬编码)

## 5. 经济覆盖(初判, Phase 4 用 SQL 落实)
sources 注册 102; category 含 finance 的比例与"官方央行源"清单待查(备份查询因引号转义未完成, Phase 4 首项补齐)。已知缺口(按 R1-R10 观察): 无 Tier1 官方源(Fed/ECB/PBOC/BIS/IMF RSS 均未注册), 中文财经覆盖依赖现有源, 无 zh↔en 查询扩展 → 中文经济词召回弱。

## 6. Serv00 资源红线(全部实测)
内存 512MB 硬上限(现用 135MB); reader 子进程 50-60MB/个(并发 2→采集窗口 1); collector 130s/10min; 磁盘 292MB/3GB; deep_search 串行读 3 页。**任何改动不得并行化 read_url、不得 node 内做 HTML 解析。**

## 7. 备份记录(本轮已做)
服务器 ~/news-project/backups-r11/: nb.db(114MB 全量备份) ab.db webui.tgz env-state.tgz; 代码 = git aa1b1d6(已推 GitHub)。回滚 = 恢复 tgz + git revert。

## 8. 用户新增需求(本轮并入)
管理后台可视化开关: 公开 REST API / /api/search / Web 登录门 三项可一键切换, 持久化于 news-data/state/feature-flags.json(文件存储, 免 DB 迁移; 误删文件=全部默认开=回滚方案)。
