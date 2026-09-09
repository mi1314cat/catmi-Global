# GITHUB_PROJECT_RESEARCH — 开源新闻聚合项目研究与复用分级

> 研究日期: 2026-09-09 · 方法: 逐项目阅读 README/源码文件/依赖清单/LICENSE + GitHub API 元数据核查（子代理并行研究，代码级验证项已标注）
> 用途: 站在现有项目肩膀上做组件选型，**不做大杂烩整合**。每个项目最终归入：直接复用 / 借鉴设计 / 放弃。

---

## 0. 技术矩阵（经代码核查后填写，非照抄预设）

| 项目 | 语言 | RSS | 网页抓取 | 正文 | 图片 | 去重 | Story聚类 | AI | SQLite | 依赖重量 | Serve00 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MuckScraper(-v2) | Python/Flask | ✓ | ✓(Playwright) | ✓ 多级回退 | ✓ | ✓ | ✓ 三级级联+pgvector | ✓(Ollama/Gemini/Groq) | ✗ | **高**(PG+pgvector+Meili+Ollama+Chromium) | ✗ 放弃部署/✓借设计 |
| Heatwire | TS/Node20+ | ✓(35源+HN) | ✗(仅RSS摘要) | ✗ | ✗ | ✓ canonical+sha256 | ✓ 质心+72h窗+seed-guard | ✓(Gemini嵌入/Claude) | ✗ | 高(Next.js+PG+pgvector) | ✗ 放弃部署/✓借设计 |
| Pharos | Python/FastAPI | ✓ | ✗(feedparser) | ✓ trafilatura | 部分 | ✓ URL规范化+SimHash | ✓ 指纹+Jaccard(无向量库) | ✓(OpenAI兼容) | ✓ hot/cold+FTS5 | 中(18直接依赖) | ⚠️ 借设计(license禁止复用) |
| news-aggregator | Node≥22.5 | ✓(含Google News RSS) | ✗ | ✗(仅摘要) | ✗ | ✓(LLM自己去重) | ✓(LLM分块聚类) | ✓(OpenAI兼容) | ✓ 内置node:sqlite | **极低**(1个依赖) | ✓ 兼容良好(参考) |
| Cruxwire | Python | ✓ | ✗ | ✗ | ✗ | ✓URL | ✓ 余弦0.74+跨源加成 | ✓(Ollama) | ✗(JSON文件) | **零依赖** | ⚠️ 参考(需适配器) |
| Beehive | Python≥3.12 | ✓ | 部分 | ✓ trafilatura | ✗ | ✓ | ✗(按频道) | ✓(Copilot SDK) | ✓ | 中(9直接) | ⚠️ 参考(3.12+Copilot门槛) |
| Evening News | Python/FastAPI | ✓ | ✓(nodriver/Chrome) | ✓ readability | ✓ | ✓ MD5(24h窗) | ✗ | ✓(Gemini原生) | ✗(PG) | 高(~25依赖+Chrome) | ✗ 放弃部署/借设计(无license) |
| Scrapling | Python | - | ✓ | ✓(markdown) | 部分(自写) | - | - | - | ✓(自适应存储) | 中(curl_cffi) | ⚠️ 解析层✓ HTTP待编译实测 |
| Crawl4AI | Python | - | ✓(浏览器) | ✓ fit_markdown | ✓ | - | - | ✓(litellm) | ✓(缓存) | **高**(Chromium+pg进程树) | ✗ FreeBSD不可运行 |

---

## 1. MuckScraper-v2（starkSV fork ← grregis/MuckScraper，MIT+版权栏瑕疵）

**架构**：Outlet(bias) → Article(Vector 768, url唯一, 抓取遥测) → Story(AI标题/摘要/deep_report) → EditionStory → Edition(早晚版)。
**三级聚类级联**（story_grouper.py）：①标题词元重叠（视频前缀剥离/停用词/同义词表，≥4共享词元+0.55-0.8重叠）→ ②pgvector 余弦（nomic-embed 768d，≥0.92 自动归组，numpy 纯 Python 回退）→ ③LLM 仲裁 0.68-0.92 灰区；方法/置信度/候选持久化 + `grouping_needs_review` 人工复核旗标。
**抓取可靠性**：正文提取多级回退链（normal → readability-lxml → canonical/print/mobile/AMP 变体 → 元数据 → RSS/API description），每篇遥测（status/method/HTTP），域名冷却 + 黑名单。
**活跃度**：fork 2026-07-15（74 commits）；上游 137★，2026-09-08 仍在推送；LICENSE 文件为 MIT 文本但 GitHub SPDX=NOASSERTION（复用前需向作者确认）。

**→ 借鉴**：Story/Edition 数据模型；三级聚类级联 + 置信度 + 人工复核旗标；抓取遥测/重试/冷却/黑名单设计；标题规范化表。
**→ 放弃**：PostgreSQL+pgvector、Meilisearch、Ollama 本地模型、Playwright、Docker、Gunicorn 多 worker（进程上限 20）。

## 2. Heatwire（NinjaCodeTurtle，MIT，2026-07-20 首发）

**架构**：sources(error_count→连续10次失败自动停用) → raw_items(sha256, canonicalUrl, AI relevance 门控) → events(质心768d HNSW, heat, sourceCount=独立域名数, whyItMatters) → daily_digests。
**聚类**：①canonical URL 精确归并 ②±72h 窗口内最近质心余弦 ≥0.9 归组 + **seed-guard ≥0.88 对比事件首条**（防质心漂移巨型簇）+ 单域名防护 ③0.85-0.90 LLM 仲裁；质心=重归一化滑动均值。
**Heat 公式**（纯 SQL，可移植 SQLite）：`heat = Σ_独立域名 best(source_weight × exp(−age_h/30h))`，96h 内事件重算，featured 需 ≥3 域名或权重≥2.0 主源。
**→ 借鉴**：heat 公式（SQLite 直接实现）；72h 窗口 + seed-guard 聚类；分层 LLM 抽象 + 3 连续失败熔断；源自动停用；JSON+RSS 双输出；"why it matters" 字段。
**→ 放弃**：Next.js 常驻 SSR（常驻进程），pgvector/HNSW（SQLite + 窗口内 Python 余弦足够），Claude Agent SDK（每次调用一个子进程 → 榨干 20 进程预算，改用纯 HTTP API）。

## 3. Pharos（nullvaluefound，⚠️ 专有 license）

**关键发现——为什么它不需要 pgvector/ES**：LLM 每篇一次抽取实体 → **命名空间加权词元指纹**（cve:15 / MITRE 12 / 人物恶意软件 10 / 公司产品 6 / 普通词 1）存 `articles.fingerprint` + `article_tokens` 倒排表；候选=±N 天窗口内共享锚点词元的 SQL 查询；得分=**仅锚点加权 Jaccard ≥0.30**；两级门槛（1 个强锚点足够；≥2 弱锚点还需上下文 Jaccard ≥0.10 防模板误聚）；每次匹配暴露 shared_tokens（可解释 UI）。采集去重独立：URL 规范化（去 utm_*）+ **64-bit SimHash**。
**工程模式**：`enrichment_status` 状态列=任务队列（pending/claimed/failed + BEGIN IMMEDIATE 事务认领）；LLM 用 `response_format=json_schema` + pydantic 校验；热/冷 SQLite 分库 + UNION 视图；FTS5 全文。
**活跃度**：16 commits，最后推送 2026-05-21，1 作者，0★。
**License 陷阱**：pyproject 自标 MIT，但 LICENSE 实为 "Pharos Proprietary License v1.1"（SPDX NOASSERTION）——**禁止复制任何代码，只允许借鉴设计**。
**→ 借鉴**：命名空间指纹+锚点 Jaccard 聚类（我们的 Story clustering 首选算法，无向量库）；SimHash 去重；状态列队列模式；"LLM 只做 enricher，不做查询时组件"。
**→ 放弃**：多用户 JWT、威胁情报专用词元、热/冷双库（我们规模用单库+FTS5 足够）。

## 4. qianqiuqiu/news-aggregator（MIT，Node≥22.5）

**极简主义**：单一运行时依赖 fast-xml-parser；SQLite 用 Node 内置 `node:sqlite`；HTTP 用内置；前端 3 个静态文件无构建。
**去重/聚类 = LLM 本身**：每源 filterFeed(并发6) → 截断 90 候选 → 分块 ≤24（并发3，块超限二分自愈）→ consolidateClusters 跨块再聚 → 每簇摘要；heat=独立媒体数。**非确定性**——两次运行结果可能不同。
**"空结果绝不保存"**（保护上一批好数据）；幂等 upsert（UNIQUE(feed_id,guid)）；30 天保留 + WAL checkpoint。
**Serve00 适配**：本机 Node v22.22.2 ≥ 22.5 ✓；~1 进程 ~50-90MB。cron 型 one-shot（collect-once.js / curate-once.js）。
**→ 直接复用（MIT）**：feed.js（RSS/Atom/Google-News 解析思路）、safe-path.js（路径穿越防护）、db.js 保留/WAL 模式、prompts/ 目录、feeds.json schema——作为参考实现移植到 Python 管道。
**→ 借鉴**：LLM 分块去重 + 二分自愈；heat=独立媒体数；cron one-shot 形态。
**→ 放弃**：无正文/图片抓取（需我们自建）。

## 5. Cruxwire（philoking，MIT，2026-06-28）

**零依赖纯 stdlib**；JSON 文件存储；Ollama 本地 API（qwen3:8b 评分+摘要+分类，nomic-embed 嵌入）。
**聚类**：余弦 ≥0.74 + 跨源加成 `min(1.5, 0.6·log2(sources))`。
**兴趣学习（无显式纠正）**：①服务端 taste 向量=最近 40 条打开/收藏嵌入质心（收藏权重 2.0），`taste_boost ≤ taste_weight(1.0)`；②浏览器端来源亲和 `clamp(1+0.10·opens+0.20·saves−0.05·dismisses, 0.5, 2.0)`，计数 7 天衰减 ×0.97。
**→ 借鉴**：taste 质心 + 来源亲和公式 + 跨源聚类加成（需 embeddings API——本系统可选用 OpenAI 兼容 embeddings）。
**→ 放弃**：无鉴权 HTTP 服务形态（Serv00 需求不同）、Ollama 本地模型。

## 6. Beehive（sinmentis，MIT，Python≥3.12，2026-08-13）

**最重要的发现——votes→few-shot 反馈环**（votes.py/prompt_builder.py）：
- SQLite `votes` 表：item_id PK 1:1，value ±1 + 可选 reason + voted_at；upsert（一票一项），取消投票即删除影响。
- 每轮排序：每频道取 ≤15 up + ≤15 down 最新投票，拼接为 `=== PAST FEEDBACK (few-shot) ===` 注入排序 prompt，旁挂用户兴趣档案 + "不要过拟合"指令。
- **零训练、零嵌入、零额外模型调用**——复用本来就要发生的排序调用；第一票就影响下一轮。
**其余**：channel/兴趣档案模型；同发布者+同标题去重；FastAPI+Jinja2 仪表盘；Copilot SDK（需换 OpenAI 兼容客户端）；外部定时器（cron 可用）。
**→ 直接借鉴（设计）**：votes 表 + few-shot 注入环（~40 行 SQL + 一段 prompt，MIT 允许近原样实现）。
**→ 放弃**：Python 3.12 要求、Copilot SDK、Azure 邮件、Research 子系统。

## 7. Evening News（Dzarlax-AI，⚠️ 无 license）

**两类"学习"**：①分类纠正 → `category_mapping` 表（ai→人工类别，usage_count 排序），推理时 top5 映射作为标签示例注入分类 prompt；②抓取学习 → `extraction_patterns`（每域 CSS 选择器，成败计数，按质量晋升）+ `domain_stability`（每域成功率，指数退避至 6h）。
**→ 借鉴**：纠正→映射示例模式；**抓取模式晋升表（与 Scrapling 自适应定位互补的另一个自动学习位）**；每域退避。
**→ 放弃**：PostgreSQL、nodriver/Chrome、Gemini 专有客户端、无 license 不能复用代码。

## 8. Crawl4AI / Scrapling 生态真实案例

| 案例 | 教训 |
|---|---|
| finviz-crawler | **curl_cffi(impersonate=chrome) 打 Cloudflare 比 Chromium 还稳**；Crawl4AI 降级为第三方全文兜底；`--single-process`+V8 256MB+每 25 分钟重启浏览器+psutil 孤儿进程清杀——浏览器是负债不是资产 |
| PicoNewsAgent | 每 URL 新建 crawler；Semaphore(3)；图片=og:image/twitter:image 优先→media 列表按 avatar/logo/ad 关键词过滤后 cap 5 |
| IT_News_Scraper | HTTP-only(RSS/Bluesky) + Scrapling DynamicFetcher(仅 Threads/X)；源连续 3 次失败自动停用；媒体 cap 10MB/20s |
| Scrapling-Job-Boards | StealthyFetcher(solve_cloudflare) + 410→headful 回退 + 逐站解析器 + 自适应选择器链回退；**GitHub Actions cron 形态**（无服务器常驻） |
| morss | 无 feedparser/requests，自写 lxml feed 解析+readability 移植+磁盘缓存——最低内存蓝图（AGPLv3，仅借设计） |
| news-please | Scrapy+newspaper4k 库 API `NewsPlease.from_urls/from_html`（标题/正文/主图/作者/日期）——通用提取参考 |
| ftr-site-config | 五万+ 站点的 XPath/CSS 规则库——"通用提取器优先，逐站配置兜底"的成熟范例 |

**生态共识（写入架构）**：HTTP-first、浏览器按站点 opt-in、双重超时（内层 10-15s + 外层 20s 硬守护）、小并发（≤3）+ 域名延迟、SQLite WAL+busy_timeout+FTS5、重试退避（1h/4h/12h 封顶）+ 连续失败自动停源、图片元数据优先+关键词过滤+大小封顶。

---

## 9. 复用 / 借鉴 / 放弃 总表

| 项目 | 直接复用(代码) | 借鉴(设计) | 放弃 |
|---|---|---|---|
| MuckScraper-v2 | - | Story 模型、三级聚类级联、遥测/冷却/黑名单 | 整个栈（PG/Meili/Ollama/Chromium/Docker） |
| Heatwire | - | heat 公式、72h+seed-guard 聚类、分层 LLM+熔断、源自动停用 | Next.js、pgvector、Agent SDK 子进程 |
| Pharos | - | 指纹+锚点Jaccard、SimHash、状态列队列 | 全部代码（专有 license） |
| news-aggregator | feed.js/db.js/prompts 思路(MIT) | LLM 分块去重、heat=独立媒体数 | Node 专属形态（我们走 Python） |
| Cruxwire | - | taste 质心、来源亲和、跨源加成 | Ollama 依赖、无鉴权服务形态 |
| Beehive | - | **votes→few-shot 环**、频道档案 | Copilot SDK、3.12 门槛 |
| Evening News | - | 纠正映射示例、抓取模式晋升 | 全部代码（无 license）+Chrome/PG |
| Scrapling | ✓ 解析层(BSD-3) | 自适应定位=网站规则自动学习 | 浏览器层(FreeBSD 不可用) |
| Crawl4AI | - | fit_markdown/结构化抽取思想 | 整个（FreeBSD 不可运行） |

---

# 增量核查（2026-09-09 第二次, GitHub API + LICENSE 原文逐项验证）

> 完整数据: `ghcheck/REPORT.md`（repo JSON/license 原文留档）· 查询日期 2026-09-09 UTC

## A. 既往 7 项目活跃度更新

| 项目 | 更新 | 对我们 |
|---|---|---|
| MuckScraper (grregis) | **高度活跃**（2026-09-08 单日 9+ commits, 0.7→1.0 soak 期）；**LICENSE 正文=标准 MIT**（此前 SPDX NOASSERTION 系误报） | ⬆️ 设计借鉴升级为"可锁 commit 借用代码" |
| MuckScraper-v2 (starkSV) | 单日创建即停滞, 转 PG+pgvector+Groq | 权重下调 |
| Pharos | 停滞 3.5 个月; **专有 license 坐实**（Proprietary v1.1） | 维持: 零代码复用 |
| Cruxwire / Beehive | MIT 已验证, 均停滞 | 维持借设计 |
| Heatwire | **仅 1 commit, 实质弃置** | heat 公式仍借（已实现在 trending.py） |
| Evening News | **无 LICENSE 文件**（8 常见名 404）+ 依赖 Chrome/CloakBrowser | 不可复制代码确认 |

## B. 用户点名新项目

| 项目 | 核查结果 | 判定 |
|---|---|---|
| **FreshRSS** | 15,958★, release 1.29.1(2026-05), 活跃; **AGPL-3.0**（LICENSE.txt 原文）; PHP≥8.1, **SQLite 内置默认**; 无需 Redis/ES/Docker/浏览器; 官方明示适用共享主机 | **只借实践参数**（AGPL 不借代码）: 条件 GET、feed 最小刷新 20min+per-feed TTL、WebSub、GUID 去重+重复标题标记 |
| open-news | = open-news-brasil/open-news（MIT, Python/Scrapy, 停滞 17 个月, 巴西单城）; archive.org "open-news API" 未查到(404) | 借"正文哈希去重" |
| YourRSS | = XimilalaXiang/YourRSS: 单日仓库, **README 自称 MIT 但无 LICENSE 文件**（反向坑）| 代码不可复制; 借 GReader API 客户端+两阶段打分思路 |
| Courier | = guardianproject/courier: GPL-2.0, **2019 年死亡** | 放弃 |

## C. 新发现（近 6 个月活跃, MIT 均经 LICENSE 文件核验）

| 项目 | 数据 | 价值 |
|---|---|---|
| **newsnext/newsnow** | 21,660★, 热点聚合+better-sqlite3/db0+**MCP 出口**（npx newsnow-mcp-server）, Node≥20 | **架构对标**; 但规避 better-sqlite3 原生编译 → 用 Node 22 内置 node:sqlite 自实现 |
| **iBigQiang/feedgrab** | 607★, Python 3.10+, 核心极轻(requests/feedparser), 重依赖 optional-extras, **多级降级取数链**, 可选 MCP(stdio) | **可复用代码**（降级链设计与我们一致） |
| **kepano/defuddle** | 9,326★, 2025-02 新, LLM-free 正文提取(linkedom, Node 22 同栈) | Node 侧提取备选（我们的正文走 Python trafilatura; 若未来 Node 统一可换） |
| richardwooding/feed-mcp | Go+官方 SDK, **SSRF 防护/熔断/缓存** | 借鉴工程模式 |
| jmanek/google-news-trends-mcp | Google News RSS 参数化 5 工具 MCP | 零 key 热点采集路线验证（与我们 gnews 用法一致） |
| **trendsmcp-ai/Trends-MCP** | **"Streamable HTTP+认证"真实范本**: 远端 /mcp + OAuth connector + Cursor 配 `headers:{Authorization: Bearer KEY}`; 代码 MIT 服务商业 | MCP 部署形态的活证据 |

## 结论修订（3 条）

1. **MCP 出口定型**: 无状态 Streamable HTTP + Bearer Token（2025-11-25 transport 为现役客户端共识; 2026-07-28 规范做双时代分支）——与 MCP_RESEARCH 报告一致。
2. **YouTube 元数据走官方频道 RSS**（自带 views/starRating）, 不碰 yt-dlp（vod2pod 的 Redis+ffmpeg 是反例）。
3. **热点源自实现**（对标 newsnow 架构, 用 node:sqlite 零原生依赖）——与我们的 Node 服务层方案完全一致, 互相印证。
