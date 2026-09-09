# GitHub 开源项目现状核查报告（查询日期：2026-09-09 UTC，供 Serv00 512MB 共享主机选型用）

**方法与数据来源**：GitHub REST API（`api.github.com/repos/{owner}/{repo}`、`/commits?per_page=10`、`/releases?per_page=1`、`/search/repositories`、`/search/issues`）+ raw.githubusercontent.com 直接抓取 LICENSE/README/配置文件原文（未使用仓库元数据的 license 判定作为唯一依据，许可证一律以 LICENSE 文件正文为准）。所有数据查询于 2026-09-09（03:11–03:55 UTC）。未做任何推测填补；查不到的字段标注"未查到"。

**指标口径**：open issues 数来自 `/repos` 的 `open_issues_count`（含 PR）；open PR 数来自 search API（`is:open is:pr`）；issues 净数 = 两者差值。"最近提交"以 commits 快照/pushed_at 为准。

---

## 任务 A — 既往 7 项目核查

### 汇总表

| # | 仓库 | 最近提交 | 最新 release | open issues / open PR | License（以 LICENSE 文件为准） | 状态变化 |
|---|------|---------|-------------|----------------------|------------------------------|---------|
| 1 | [grregis/MuckScraper](https://github.com/grregis/MuckScraper) | **2026-09-08**（单日 9+ commits） | v0.6.0-beta（2026-08-08，prerelease） | 2 / 0 | **MIT**（LICENSE 正文为标准 MIT，"(c) 2026 grregis"；仓库元数据因文件首行标题而误报 NOASSERTION） | 高度活跃，0.7.0-beta→1.0 稳定期（soak） |
| 2 | [starkSV/MuckScraper-v2](https://github.com/starkSV/MuckScraper-v2) | 2026-07-15 | 无 release | 0 / 0 | **MIT**（LICENSE 文件与 grregis 版完全相同） | 自 7-15 起停滞；为 MuckScraper 的分叉改版 |
| 3 | [nullvaluefound/Pharos](https://github.com/nullvaluefound/Pharos) | 2026-05-21 | 无 release | 0 / 0 | **专有**：Pharos Proprietary License v1.1（2026-05），明确"NOT open-source under OSI definition" | 停滞 ~3.5 个月；5-21 最后一次提交就是"Update LICENSE" |
| 4 | [philoking/Cruxwire](https://github.com/philoking/Cruxwire) | 2026-06-28 | v1.0.0（2026-06-25） | 2 / 1（合计 3） | **MIT**（"(c) 2026 Jason Burns"，已验证） | 停滞 ~2.5 个月（updated_at 2026-09-03 仅元数据变动） |
| 5 | [sinmentis/Beehive](https://github.com/sinmentis/Beehive) | 2026-08-13 | 无 release | 0 / 0 | **MIT**（"(c) 2026 Beehive contributors"，已验证） | 中等活跃（7-14→8-13 连续推进），近 1 个月无提交 |
| 6 | [NinjaCodeTurtle/Heatwire](https://github.com/NinjaCodeTurtle/Heatwire) | 2026-07-20（**仅 1 个 commit**："initial public release"） | 无 release | 0 / 0 | **MIT**（已验证） | 一次性发布后停滞，实质弃置 |
| 7 | [Dzarlax-AI/Evening-News](https://github.com/Dzarlax-AI/Evening-News) | 2026-08-21 | 无 release | 0 / 0 | **无 LICENSE 文件**（尝试 LICENSE/LICENSE.md/LICENSE.txt/COPYING 等 8 个常见名均 404；README 亦无 License 章节；元数据 license=null）→ 默认保留所有权利 | 低频维护（4-14 前端重构、5-27/6-14 PR、8-19/8-21 修复） |

### 逐项核查细节

**1. grregis/MuckScraper** — 137★/13 forks，Python，topics: docker/flask/llm/ollama/political-bias。改名：无（API 无重定向）；归档：否。近期提交显示一次**中等规模重构**："Split aggregator/blueprints/admin.py into a package"（2026-09-08），并出现 "upgrade-contract policy" 文档、"0.7.0-beta → 1.0 soak tracking"（本地文件）、标题 token 归一化 memoize 性能优化、"entity-veto guardrail"（国家不匹配的聚类否决）。CHANGELOG 已写入 0.7.0-beta 发布说明，但 **GitHub release 仍停在 v0.6.0-beta**。来源：`api.github.com/repos/grregis/MuckScraper`、`/commits`、`/releases`；LICENSE `raw.githubusercontent.com/grregis/MuckScraper/main/LICENSE`。

**2. starkSV/MuckScraper-v2** — 0★，2026-07-15 当天创建并完成全部提交。技术栈与上游分叉：**Postgres + pgvector（钉在 0.4.2）+ SQLAlchemy + Groq/Gemini/Ollama 三 provider**，RSS/话题重心改为 homelab/AI/dev-tools，"morning edition 5am-4:59pm ET"。同名 MIT LICENSE 文件原样继承。停滞至今。对本项目无新增价值（栈更重、无人维护）。

**3. nullvaluefound/Pharos** — 0★/2 forks，Python，威胁情报聚合（MITRE ATT&CK 映射、确定性聚类）。**许可证关键事实**：LICENSE 正文 12.7KB，为 "PHAROS PROPRIETARY LICENSE v1.1, May 2026"：仅允许个人（自然人）在自购/自租硬件上自用自托管，禁止再分发/转许可/商业使用；另设"雇主例外"（Owner 现任/前雇主的内部使用许可）。当前 README License 章节已明确写 "Pharos is proprietary software"（但其引用的是 v1.0，LICENSE 实为 v1.1 —— 文档内部小不一致）。**历史上"自称 MIT"的痕迹已不存在于当前文件中**（5-01 有 "license: extend employer carve-out … (v1.1)"、5-21 "Update LICENSE"）。停滞自 2026-05-21。结论不变且加强：只可借鉴设计思想（聚类/报告管线），代码**不可复用**；自托管个人使用在许可证 1(c) 下是允许的。

**4. philoking/Cruxwire** — 4★，主语言 HTML（模板为主），本地 LLM 私有 RSS 阅读器（Ollama/embeddings/去重/摘要），homepage cruxwire.app，topics 含 docker/selfhosted/rss-reader。v1.0.0 于 2026-06-25 发布，6-28 后无提交；7 个已合并 PR（#4–#13）均为 UI 微调。open：2 issues + 1 PR。

**5. sinmentis/Beehive** — 2★，Python/FastAPI/**SQLite**（topics 明示），聚合 RSS/Reddit/HN/Google News，多语言邮件摘要。8 月上旬持续提交（fetch 调度日历、digest 去重 "suppress repeated news in digests"、readability 改进），8-13 后停滞。0 issue/0 PR（社区几乎为零）。

**6. NinjaCodeTurtle/Heatwire** — 1★，TypeScript/Next.js/**Postgres + pgvector**，单 commit 一次性放出（含 "agent API" 概念）。无社区、无后续。实质弃置。

**7. Dzarlax-AI/Evening-News** — 1★，Python/FastAPI，俄语摘要 + Telegram 投递，**依赖 Chrome/CloakBrowser 浏览器会话**（近期提交 "support CloakBrowser browser service"、"Fix Chrome session lifecycle and bounded recovery (#7)"）。2023 年老仓库恢复维护但无许可证。对 Serv00（无浏览器、进程数 20 上限）严重不友好。

---

## 任务 B — 新项目完整调查

### 7. FreshRSS（FreshRSS/FreshRSS）✅ 全项查清

- **GitHub URL**: https://github.com/FreshRSS/FreshRSS
- **License SPDX**：**AGPL-3.0**（LICENSE 文件名为 `LICENSE.txt`，34,524 字节，正文为完整 GNU Affero GPL v3 文本，已核验原文；composer.json 亦声明 AGPL-3.0）
- **最近提交**：2026-09-08（edge 分支持续滚动，`constants.php` 显示 1.29.2-dev）
- **最近 release**：**1.29.1**（2026-05-20；1.29.1 为 1.29.0 的 bugfix 版）
- **issue+PR 活跃度**：open 662（含 PR；**open PR=100** → 约 562 open issues）。15,958★ / 1,273 forks。健康度：极高（官方分版滚动 edge + 周期性 versioned release）
- **语言/运行时**：PHP；**要求 PHP ≥ 8.1**（`composer.json` `require.php: >=8.1`，`constants.php` `FRESHRSS_MIN_PHP_VERSION='8.1.0'`）；必需扩展含 **pdo_sqlite**、curl、dom、mbstring、intl 等（composer.json 原文）
- **数据库**：官方文档 DatabaseConfig.md："FreshRSS supports the databases **SQLite (built-in)**, PostgreSQL, MariaDB / MySQL" —— SQLite 为内置默认；代码层有全套专用 DAO（`app/Models/{Category,Entry,Feed,Stats,Tag}DAOSQLite.php`、`app/SQL/install.sql.sqlite.php`）
- **Redis/ES/向量库**：**均不需要**（仅 bundled SimplePie 内含 Redis cache 适配器文件，属可选组件，非依赖）
- **Docker**：可选（Docker 镜像内置 cron `CRON_MIN`）；**非 Docker 部署路径成熟**：cron / systemd timer / 在线 cron 触发 `./app/actualize_script.php`（docs/en/admins/08_FeedUpdates.md）
- **浏览器**：不需要（服务端 PHP Web 应用）
- **资源消耗/512MB 适配**：官方 Prerequisites 明确 "requirements are really low … should run on most **shared host** servers"；无守护进程（cron 拉起脚本即退出），**非常适合共享主机**（但 PHP 栈与本系统 Python/Node 不同栈）
- **成熟做法要点（本项目最关心）**：
  - **Conditional GET**：由 FreshRSS 维护的 SimplePie 分叉实现（vendor 于 `lib/simplepie/simplepie/`；该分叉 [FreshRSS/simplepie](https://github.com/FreshRSS/simplepie) 最近推送 2026-09-08，活跃）；CHANGELOG 有条件请求回归修复记录（主仓 #7403 ↔ FreshRSS/simplepie#33）
  - **Feed 发现**：由内置 SimplePie 分叉承担解析与自动发现；1.29.1 新增支持 `.txt` URL 列表直接导入订阅（除 OPML 外）
  - **去重**：条目以 GUID 为同一性；另有"标记重复标题为已读"功能（历史修复 #6664）；WebSub 推送侧去重（如 WordPress.com HTTP duplicates 修复）
  - **刷新调度**：`actualize_script.php` + cron/systemd/webcron；**单 feed 最小刷新间隔 20 分钟**（脚本内置）；每 feed 自带 TTL/refresh interval（OPML 导入导出含 TTL，#8982）；actualize 互斥锁改进支持多实例（#9045）
  - **SQLite 支持现状**：一等公民且持续维护 —— 1.29.1 新增"自动周期 SQLite 导出 CLI（含保留策略）"（#8819）、Web UI 下载 SQLite 库（#6931/#8169）；但**搜索能力分库差异**：高级 regex 语法依赖所用数据库，PostgreSQL 可用 `pg_trgm` GIN 索引加速标题/正文/作者检索（DatabaseConfig.md），SQLite 无此加速路径
- **结论**：**只借鉴**（PHP+AGPL 不并入代码）：借鉴 conditional GET 落地方式（自维护解析器分叉）、per-feed TTL + 20 分钟下限的调度参数、SQLite 备份/保留策略、以及"共享主机低要求"的工程姿态。
- 来源：`api.github.com/repos/FreshRSS/FreshRSS`（+ /commits、/releases）、`raw.githubusercontent.com/FreshRSS/FreshRSS/edge/{LICENSE.txt, composer.json, constants.php, docs/en/admins/02_Prerequisites.md, docs/en/admins/08_FeedUpdates.md, docs/en/admins/DatabaseConfig.md, CHANGELOG.md}`、`github.com/FreshRSS/simplepie`

### 8. open-news — 已甄别，最相关 = open-news-brasil/open-news

GitHub 上 `open-news` 同名者 582 个；按"新闻聚合"相关性筛选：
- **选定：[open-news-brasil/open-news](https://github.com/open-news-brasil/open-news)**（名称完全匹配 + 聚合方向）
  - License SPDX：**MIT**（LICENSE 文件核验："(c) 2024 João Paulo Carvalho" 标准 MIT 文本，非元数据推断）
  - 最近提交：2025-04-05（**停滞 ~17 个月**）；最近 release：无；open issues 5 / PR 0
  - 语言/运行时：Python（poetry，`requires-python ^3.11` ✓ 与 Serv00 Python 3.11 匹配）；依赖 Scrapy 2.11、**pysondb-v2（JSON 文件库，非 SQLite）**、boto3、taskipy；dev 才用 scikit-learn
  - Docker：Dockerfile 基于 python:3.12-alpine + 容器内 crond 每 10 分钟（Docker 非必需，逻辑可直接用 cron 复刻）
  - 浏览器：不需要（纯 Scrapy）
  - 资源：单城市（巴西 Parnaíba-PI 地区 11 个本地站点的定向爬取），量级极小
  - 512MB 适配：技术上可行，但**项目死寂、范围窄、DB 用 JSON 文件**
  - 可复用性：**只借鉴** —— 其"news hash calculator"（基于正文内容哈希去重，2025-04 的最后两个功能提交）与"消息内容指纹 → 去重 ID"思路可借鉴
- 备选说明：
  - **archive.org 的 "open-news API"**：**未查到**。`https://archive.org/details/opennews` 返回 404；Internet Archive 的相关服务是 **TV News Archive**（https://archive.org/details/tv，300 万+美国电视广播字幕检索），其旧 API 端点（`archive.org/services/tv/v1/beta.json`、`archive.org/services/tv`）在本次核查中均返回 404（端点已变动/迁移，无法给出稳定引用）。
  - 活跃的近似名项目（供参考，未列为正式对象）：anomixer/openclaw-news（JS，41★，pushed 2026-09-09，Ollama+Telegram 每日新闻）；jacob-bd/openclaw-newsroom（Python，173★，pushed 2026-06-08，5 数据源+Gemini 编辑策展）；eracle/OpenOutNews（Python，pushed 2026-09-08，explore/exploit 式 newsletter 策展）。

### 9. YourRSS — 已甄别，最相关 = XimilalaXiang/YourRSS

- **GitHub URL**: https://github.com/XimilalaXiang/YourRSS（另一同名 Hyunndy/YourRSSNewsReader 为 2020 年韩文安卓阅读器，已死）
- **License SPDX**：**无 LICENSE 文件**（仓库仅 11 个文件，无 LICENSE；README 声称 "License: MIT" 但**无授权文件背书**；GitHub 元数据 license=null）→ **法律上默认保留所有权利，不可复制其代码**，属"README 自称 MIT、文件缺失"的反向坑
- **最近提交/活跃度**：整个仓库的所有提交集中在 **2026-04-06 一天**（从 [HarrisHan/ai-daily-digest](https://github.com/HarrisHan/ai-daily-digest) fork 改造而来）；之后无提交；无 release；0 issue/0 PR；3★
- **语言/运行时**：JavaScript（Node ≥ 18，README "Requirements" 明示）；**零 npm 依赖**（5 个 `.mjs` 脚本直跑）
- **数据库**：无自有 DB —— **构建在自托管 FreshRSS 之上**，经 Google Reader API（GReader）读写（`scripts/fetch-freshrss.mjs`）；个性化依赖外部 **Cortex Memory** 服务（rikouu/cortex）；可选 Blinko 知识库
- **Redis/ES/向量库/Docker/浏览器**：均不需要（轻量脚本）；但**依赖 FreshRSS + Cortex 两个外部服务**才完整工作
- **512MB 适配**：脚本本身极轻（Node 22 可跑）；整体是"Agent skill + CLI 管道"（SKILL.md 面向 OpenClaw/Cursor/Claude Code），不是常驻服务
- **可复用性**：**只借鉴** —— 有价值的点：① GReader API 端点用法（未读流、按 24h/48h 时间窗、category 过滤、subscribe/unsubscribe）；② 两阶段打分（全量轻打分 → Top-N 精摘要）+ 批量/并发参数化；③ like/dislike → 偏好回灌。代码不可复制（无授权文件）
- 来源：`api.github.com/repos/XimilalaXiang/YourRSS`、`git/trees?recursive=1`、raw README.md

### 10. Courier — 已甄别，最相关 = guardianproject/courier

- **GitHub URL**: https://github.com/guardianproject/courier（搜索确认这是"新闻阅读方向"的唯一 Courier；其余同名均为消息网关/Scala 库/包裹跟踪等）
- **定位**：Guardian Project 出品的**安卓安全新闻阅读器**（"Courier, a secure, private news reader"，Java）
- **License SPDX**：LICENSE 文件 666 字符，正文为 **GNU GPL v2** 头部声明（"GNU General Public License version 2"）；仓库元数据 NOASSERTION
- **最近提交**：2019-04-01（**死亡 ~7 年**）；最近 release：v2.0.0-zip-alpha.1；open issues 3 / PR 0；10★
- **运行时/数据库/依赖**：Android（build.gradle 3.3.2 时代），服务端栈无从谈起
- **512MB 共享主机适配**：**不适用**（移动端项目）
- **可复用性**：**放弃**（仅历史意义上可看其 OPML 离线包/隐私设计思路）
- 来源：`api.github.com/repos/guardianproject/courier`、raw LICENSE/build.gradle

---

## 任务 C — 自主发现（6 个，近 6 个月均有推送）

### C1. newsnext/newsnow —— 热点聚合 + SQLite + 官方 MCP 出口的标杆
- **URL**: https://github.com/newsnext/newsnow （由 ourongxing/newsnow 迁移至 newsnext org；package.json homepage 仍指旧地址）
- **数据**：21,660★ / 156 open issues（含 PR）/ 创建 2024-09-23 / 最近推送 **2026-07-07** / TypeScript / MIT（LICENSE 文件核验，© ourongxing）/ 创建于 2024-09
- **一句话**：实时热点新闻聚合器（知乎/微博/V2EX/HN/GitHub Trending 等），"Elegant reading of real-time and hottest news"
- **技术栈**：Node ≥ 20（vite + h3 + React 19）；**better-sqlite3 + db0**（本地 SQLite；也推荐 Cloudflare D1）；无 Redis/ES；Docker 可选（node:20-alpine，也可 `node dist/output/server/index.mjs` 裸跑）；GitHub OAuth 登录 + JWT；30 分钟默认缓存 + **自适应抓取间隔（下限 2 分钟，防封禁）**；数据源适配器集中在 `shared/sources` + `server/sources`，类型完备、结构清晰
- **MCP**：README 明示 "support MCP server"：通过独立 npm 包 **newsnow-mcp-server**（stdio，`npx -y newsnow-mcp-server` + `BASE_URL` 指向自建实例；npm 上 v0.0.12，另有多个社区分叉包）
- **注意**：README 自述"当前为仅中文的 demo 版，完整版即将发布且**不再接受贡献**"
- **与本项目关系**：**高价值借鉴 + 部分可复用**（MIT）—— ① 源适配器架构与"热点源"清单；② SQLite 缓存/自适应抓取参数；③ "聚合服务 + 外挂 MCP 包（BASE_URL 指回自身）"的发布形态。整体部署受限于 better-sqlite3 原生模块在 FreeBSD 需本地编译 + SSR 应用内存占用，不建议整体上 Serv00。

### C2. iBigQiang/feedgrab —— 多平台采集 + 可选浏览器 + 可选 MCP 的分层设计
- **URL**: https://github.com/iBigQiang/feedgrab
- **数据**：607★ / 11 open issues / 创建 2026-02-26 / 最近推送 **2026-09-08**（v0.26.2，活跃）/ Python ≥ 3.10（✓3.11）/ MIT（LICENSE 文件核验 © Leo）
- **一句话**："18+ 主流自媒体与内容平台一站式抓取"，统一输出 Obsidian 兼容 Markdown
- **技术栈**：**核心依赖极轻**：requests、feedparser、python-dotenv、loguru；重依赖全部做成 optional-extras：playwright（浏览器）、telethon（Telegram）、mcp[cli]、XClientTransaction/xhs/feishu 等；平台 YouTube 走 **InnerTube API → yt-dlp 字幕 → YouTube Data API v3**，X/Twitter 走 "GraphQL → FxTwitter → Syndication → oEmbed → Jina → Playwright" 多级降级链；微信/小红书等中文平台依赖 Playwright/Jina 兜底
- **MCP**：可选第三层（`mcp_server.py`，stdio，`pip install -e ".[mcp]"` 后 `python mcp_server.py`），另配 Claude Code 技能包
- **浏览器**：**可选**（核心 RSS/API 路径不需要；中文社媒深度抓取需要）
- **512MB 适配**：核心路径完全适配（pip 安装、无 DB 依赖）；启用 Playwright 的路径不适配（Serv00 无浏览器且进程受限）
- **与本项目关系**：**可复用设计 + 可复用代码**（MIT、纯 Python）——多级降级取数链、optional-extras 依赖分层、MCP/技能双出口形态直接可借。

### C3. kepano/defuddle —— 2025 新一代 LLM-free 正文提取（Node 栈）
- **URL**: https://github.com/kepano/defuddle
- **数据**：9,326★ / 81 open issues / 创建 **2025-02-27** / 最近推送 **2026-09-04** / TypeScript / MIT（LICENSE 核验 © 2025 Steph Ango/@kepano，Obsidian CEO）
- **一句话**："Get the main content of any page as Markdown" —— 为 Obsidian Web Clipper 造的正文提取器，定位为 Mozilla Readability 替代品
- **技术栈**：运行时依赖极小（commander；可选 linkedom/turndown/temml）；提供 `defuddle/node` 接受任意 DOM 实现（推荐 linkedom，无浏览器、无 jsdom 重依赖）；Node 22 完全适配；**无 LLM**；额外提取 schema.org 等结构化元数据；README 自述 "very much a work in progress"
- **512MB 适配**：✓（内存足迹小、单进程、无浏览器）
- **与本项目关系**：**可复用**（MIT，Node 22 同栈）——作为 RSS 之外的"原文正文/元数据提取"引擎候选；与 Python 侧 trafilatura 对应。

### C4. richardwooding/feed-mcp —— 工程质量最好的开源 feed→MCP 服务器
- **URL**: https://github.com/richardwooding/feed-mcp
- **数据**：34★ / 8 open issues / 创建 2025-05-30 / 最近推送 **2026-09-08** / Go 1.27 / MIT（LICENSE 核验 © 2025 Richard Wooding）
- **一句话**：把 RSS/Atom/JSON feed 带进 Claude 的 MCP 服务器（Claude Desktop 直接读新闻/博客）
- **技术栈与工程点**：使用**官方 modelcontextprotocol/go-sdk v1.7.0** + gofeed；**ristretto 缓存 + gobreaker 熔断 + ssrfguard（SSRF 防护）+ colly**；README 展示的部署形态为 Docker `docker run -i`（stdio 传输）或二进制；未见 HTTP 远程端点文档
- **512MB 适配**：Go 单二进制极轻，但 Serv00 运行时列表未含 Go —— 以借鉴为主
- **与本项目关系**：**只借鉴** —— 三条可移植的工程模式：feed 拉取必须过 SSRF 防护、外部源调用加熔断、结果做进程内缓存。

### C5. jmanek/google-news-trends-mcp —— Google News RSS + Trends RSS 的 MCP 化范例
- **URL**: https://github.com/jmanek/google-news-trends-mcp（PyPI: `google-news-trends-mcp`）
- **数据**：89★ / 2 open issues / 创建 2025-06-28 / 最近推送 **2026-08-11** / Python / MIT（LICENSE 核验 © 2025 Jesse Manek）
- **一句话**："slurps data from Google News and Google Trends RSS endpoints"，5 个 MCP 工具：按关键词/地区/主题取新闻、取头条、取指定地区热门搜索词；可选 LLM sampling 摘要
- **技术栈**：纯 RSS 抓取（Google News RSS 参数化：keyword/location/topic/top + Google Trends daily trends RSS），stdio 传输（uvx/pip 直跑），轻依赖
- **512MB 适配**：✓（但它是 stdio MCP，通常由 agent 侧拉起）
- **与本项目关系**：**可复用思路** —— 证实"Google News RSS（多地区/多主题/多语言参数化 URL）+ Trends RSS"是零 key、零浏览器的全球热点采集最省力路径；5 工具划分可直接映射到我们的 MCP 工具面。

### C6. trendsmcp-ai/Trends-MCP —— "Streamable HTTP + 认证"远程 MCP 部署的真实范例 ⭐
- **URL**: https://github.com/trendsmcp-ai/Trends-MCP（PyPI: `trends-mcp-server`；托管服务 https://www.trendsmcp.ai）
- **数据**：37★ / 2 open issues / 创建 2026-03-21 / 最近推送 **2026-08-29** / Python / MIT（LICENSE 核验 © 2026 trendsmcp —— 注意：**MIT 的是其代码/客户端，托管服务本身为商业 SaaS**，免费档 100 请求/月）
- **一句话**：为 agent 提供 Google/TikTok/YouTube/Reddit/Amazon/Wikipedia/新闻情绪等 30+ 源的实时趋势数据（"One MCP connection, one API key"）
- **部署形态（用户最关心的"怎么用 Streamable HTTP + 认证"）**：
  - 远程 MCP 端点：`https://www.trendsmcp.ai/mcp`（Claude/ChatGPT connector 用 **OAuth** 授权连接）
  - Cursor/VS Code 的安装深链显示原始配置：`{"url":"https://api.trendsmcp.ai/mcp","transport":"http","headers":{"Authorization":"Bearer YOUR_API_KEY"}}` —— 即 **HTTP 传输 + Bearer API Key 头**
  - 同时保留 stdio 形态（PyPI 包），README 徽章自述 "MCP: remote + stdio"
- **行业背景**（佐证该形态是 2026 主流）：MCP 规范已转向**无状态 Streamable HTTP**（2025-11-25 transport；Cloudflare "下一代 MCP" 的 `/mcp` 端点同时接受新协议与 stateless 请求；Microsoft 2026 文章描述 stateless HTTP 模式横向扩展）。参考：[MCP Transport Future（2025-12-19）](https://blog.modelcontextprotocol.io/posts/2025-12-19-mcp-transport-future/)、[Cloudflare: The next generation of MCP](https://blog.cloudflare.com/mcp-v2/)、[Microsoft: MCP Just Went Stateless](https://techcommunity.microsoft.com/blog/appsonazureblog/mcp-just-went-stateless-%E2%80%94-what-the-2026-spec-changes-about-scaling-on-app-servic/4530222)
- **与本项目关系**：**只借鉴（形态范本）** —— 我们在 Serv00 上做"新闻+搜索+趋势 MCP"时：单进程 HTTP 服务暴露 `/mcp`、无状态 Streamable HTTP、`Authorization: Bearer` 头做简单认证（自建 key），即当前生态的通行做法。

### 次要发现（不占 6 席，一句话带过）
- **6551Team/opennews-mcp**（2,131★，Python，MIT，pushed 2026-08-18）：MCP 薄客户端（mcp[cli]+httpx+websockets 三依赖），**数据来自 6551.io 托管加密货币新闻 API（注册 token）**，stdio+WebSocket；2026-02-26 创建即冲高 2 千星，营销痕迹明显 —— 借鉴其"env token 认证 + 薄客户端"形态即可。
- **ma2za/google-news-api**（18★，Python，pushed 2026-09-04）：Google News RSS 的异步 Python 客户端（搜索/头条/URL 解码）—— 若走 Python 栈可直接 pip 复用。
- **baozi13250127/news-aggregator-trae**（2★，pushed 2026-08-29，**无 LICENSE 文件**）：Flask+SQLite+feedparser+DeepSeek 打分+字符 trigram Jaccard 事件聚类+schedule 调度，与我们目标栈几乎同构 —— 因无许可证**只能借鉴**（其 `INSERT OR IGNORE` 去重、AI 失败规则兜底、聚类阈值 0.3–0.95 参数化可参考）。
- **wotiler-star/global-headlines**（0★，TypeScript，pushed 2026-09-08）：Next.js 15 + **node:sqlite**（零原生依赖的 SQLite）多语言聚合 —— 验证了 Node 22 内置 sqlite 路线可行。
- **mxpv/podsync**（YouTube/Vimeo→播客 RSS，Go）与 **madiele/vod2pod-rss**（见下 C7 备选）：YouTube 频道 → RSS 的两条成熟路径。
- **FeedNest**（远程 MCP，26 工具，RSS/YouTube/播客/Google News，remote-only，见 [r/mcp 展示帖](https://www.reddit.com/r/mcp/comments/1wao41z/showcase_a_remote_mcp_server_for_your_feeds_and/) 与 [getlulu.dev 收录页](https://getlulu.dev/mcps/feednest)）：**未找到开源仓库** —— 证明"个人订阅源作为远程 MCP 暴露"这一产品形态成立。
- 提取器老三样现状（活跃度快照，2026-09-09）：adbar/trafilatura 6.8k★ pushed 2026-08-28；codelucas/newspaper 15.2k★ pushed 2026-08-31；mozilla/readability 11.4k★ pushed 2026-08-04；kingname/GeneralNewsExtractor 3.8k★ pushed 2026-04-21。

> 补充说明（C7 备选 madiele/vod2pod-rss，384★，Rust，MIT，pushed 2026-08-31）：YouTube/Twitch 频道→播客 RSS。**依赖 Redis（cached redis_tokio）+ 服务端实时 ffmpeg 转码（Raspberry Pi 3-4 级别测试）**，且建议 Docker 部署 —— **不适合 512MB 共享主机**；可借鉴点仅一条：元数据走 YouTube Data API v3 / 频道 RSS（youtube.com/feeds/videos.xml），**服务端不下载视频**，这也是"不依赖 yt-dlp 重型依赖"的正解。

---

## 对本项目的影响更新（既往结论修正）

1. **MuckScraper（grregis）结论微调：从"只借设计"→"设计与代码皆可借（MIT 已验证）+ 活跃度正面"**。它仍高度活跃（2026-09-08 当天 9+ commits）、正处 0.7.0-beta→1.0 稳定期，且 LICENSE 文件正文为标准 MIT（元数据的 NOASSERTION 是解析误报）。但注意其 9 月重构（admin.py 拆包）说明内部结构仍在动，**直接复制代码要锁 commit**；其对本地 Ollama 的依赖在 Serv00 上不可行，维持不部署。
2. **starkSV/MuckScraper-v2 权重下调**：单日创建即停滞、0 社区、技术栈转向 Postgres+pgvector（与 Serv00 仅 SQLite 冲突）。此前若参考它，改回只参考 grregis 主线。
3. **Pharos 结论加强且加约束**：LICENSE 正文 v1.1 明确专有（README 引用 v1.0 有笔误）；停滞 3.5 个月。**代码零复用**；自托管个人使用许可成立（1(c)），但不得再分发或去除品牌。其"确定性聚类/ATT&CK 映射/成本上限"设计思想仍值得抄结构。
4. **Cruxwire / Beehive / Heatwire**：三者 MIT 均已从 LICENSE 文件验证。Cruxwire（v1.0.0 后停滞）、Beehive（SQLite+FastAPI，最接近我们栈，8-13 后停滞）维持"借设计/可选择性借码"；**Heatwire 实质弃置**（单 commit）+ Postgres 栈，借鉴权重降为最低。
5. **Evening-News 结论强化**：无 LICENSE 文件（README 亦无授权章节）→ **代码不可复制**；近期提交证实其依赖 Chrome/CloakBrowser 会话，与 Serv00 无浏览器/20 进程上限直接冲突。仅借鉴其"邮件/Telegram 投递 + 每日额度上限（NEWS_LIMIT_*）"想法。
6. **新增可对标 FreshRSS 的成熟实践**（此前 7 项目均无此层级参照）：conditional GET（自维护解析器分叉）、feed 最小刷新间隔（20 min）+ per-feed TTL、WebSub 推送、SQLite 一等公民（含周期导出/保留策略 CLI）、共享主机低要求承诺。AGPL+PHP → **只借实践参数，不借代码**。
7. **MCP 出口形态定型**：2026 生态共识是**无状态 Streamable HTTP + Bearer/OAuth**（Trends-MCP 的 `transport:http + Authorization: Bearer` 配置、Claude/ChatGPT connector OAuth；MCP 规范 2025-11-25 transport；Cloudflare/微软的部署文章）。我们的 MCP 工具面建议照此实现；stdio 形态（feed-mcp、google-news-trends-mcp、opennews-mcp、YourRSS 的 skill）只作为本地 agent 场景补充。
8. **采集侧新增两条省力路线**：① Google News RSS 参数化（多地区/主题/语言，零 key 零浏览器，google-news-trends-mcp 与 ma2za/google-news-api 双双验证其可行性）；② YouTube 元数据走官方频道 RSS（`feeds/videos.xml?channel_id=`）+ Data API v3，**不要引入 yt-dlp/浏览器**（vod2pod 反例：Redis+ffmpeg）。
9. **正文提取候选定型**：Node 栈用 **defuddle**（2025 新，MIT，linkedom 无浏览器，Node 22 同栈），Python 栈备选 trafilatura（活跃，LLM-free）——比 newspaper3k/readability 更现代，且与"不要浏览器"的约束一致。
10. **热点源适配器可直接对标 newsnow**：其 `server/sources` 目录 + 自适应抓取间隔（≥2min）+ 30min 缓存 + SQLite 存储的组合是"Serv00 可承受的热点聚合"最接近的开源参照（MIT）；但整体部署受 better-sqlite3 原生编译与 SSR 内存影响，建议**抄架构、自实现**（或用 Node 22 内置 `node:sqlite` 规避原生模块，见 wotiler-star/global-headlines 的先例）。

---

### 附：本次全部数据来源清单（均于 2026-09-09 UTC 查询）
- API：`api.github.com/repos/{grregis/MuckScraper, starkSV/MuckScraper-v2, nullvaluefound/Pharos, philoking/Cruxwire, sinmentis/Beehive, NinjaCodeTurtle/Heatwire, Dzarlax-AI/Evening-News, FreshRSS/FreshRSS, FreshRSS/simplepie, open-news-brasil/open-news, XimilalaXiang/YourRSS, guardianproject/courier, newsnext/newsnow, iBigQiang/feedgrab, kepano/defuddle, richardwooding/feed-mcp, jmanek/google-news-trends-mcp, trendsmcp-ai/Trends-MCP, 6551Team/opennews-mcp, madiele/vod2pod-rss, baozi13250127/news-aggregator-trae}` 及各自 `/commits?per_page=10`、`/releases?per_page=1`、`/git/trees`；`/search/repositories`（名称甄别与主题发现）；`/search/issues`（open PR 计数）
- LICENSE 原文（raw.githubusercontent.com，逐文件核验）：上列各仓 LICENSE/LICENSE.txt/COPYING 路径；FreshRSS 为 `LICENSE.txt`
- 文档原文：FreshRSS `composer.json`、`constants.php`、`docs/en/admins/{02_Prerequisites,08_FeedUpdates,DatabaseConfig}.md`、`CHANGELOG.md`
- 网页/外部：npmjs.com/package/newsnow-mcp-server；archive.org/details/tv（与 404 的 opennews 端点探测）；blog.modelcontextprotocol.io/posts/2025-12-19-mcp-transport-future/；blog.cloudflare.com/mcp-v2/；techcommunity.microsoft.com（MCP stateless, 2026）；reddit.com/r/mcp（FeedNest showcase）；getlulu.dev/mcps/feednest
- 原始 JSON/抓取件留档：`/root/deepseek1/ghcheck/`（repo_*.json、license_*.txt、taskB_*/taskC_* 文件、REPORT.md）
