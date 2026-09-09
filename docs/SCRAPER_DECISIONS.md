# SCRAPER_DECISIONS — 技术决策记录（含被否方案）

> 每条决策都有 Serve00 实测数据或上游证据支撑；反事实（"如果不这样做"）一并记录。

## D1. 抓取主力 = httpx + trafilatura（而非 Scrapling Fetcher）
**决定**: HTTP 层用系统已有的 httpx；正文用 trafilatura。
**依据**: curl_cffi `detect_arch()` 直接 `Exception: Unsupported arch: FreeBSD`（install_report 步骤 4/5 双重验证）——Scrapling 的 HTTP 引擎在本机物理不可用；httpx/trafilatura 零成本可用且实测（BBC 226KB 页 fetch 0.34s + extract 0.25s，峰值 105MB）。
**代价**: 失去 TLS 指纹伪装（curl_cffi impersonate）。对主流新闻站影响有限（BBC/NPR/Google News 实测全通）；对强反爬站（Reuters 等）若 403 → 交给 S4 站点规则或放弃。
**回退触发**: 若未来某站必须 TLS 伪装 → 该站走外部渲染服务，不在本机装。

## D2. Scrapling = 解析/自适应层（而非完整框架）
**决定**: 保留 scrapling 0.4.15 用于: Selector 解析兜底、`Response.markdown()`（[rag]）、**自适应元素定位**（save/retrieve/relocate → 网站规则自动学习）。
**依据**: 解析层实测全 PASS（33-56MB）；自适应 API 实测可用；BSD-3 许可干净。
**锁定**: 版本锁 0.4.15（0.4.x 有破坏性 API 变更史：Adaptor→Selector、css_first→css().first）。

## D3. Crawl4AI = 本机放弃（明牌）
**依据**: playwright 在 FreeBSD 上 `versions: none`（PyPI 无 wheel 无 sdist）；唯一打包路径需 root 开 Linuxlator 且 Chrome broken；内存（社区报告 >1GB/次）也超限。
**替代**: JS 站点三级策略——S4 站点规则（XHR/JSON）→ S5 外部渲染服务（可选、默认关）→ 放弃该源。
**翻案条件**: 用户将来提供一台 Linux VPS 跑 Crawl4AI API 时，S5 才启用。

## D4. 数据库 = SQLite（WAL + FTS5）
**依据**: 实测原型建表+写入全通过；Pharos/Heatwire/beehive/news-aggregator 四个参照项目全部证明该规模 SQLite 足够；Serv00 平台 MySQL/PG 虽可申请但无 pgvector、无必要。
**设计**: 单库 + WAL + busy_timeout=5000 + FTS5 全文索引；每日快照由平台 ZFS 兜底。

## D5. Story 聚类 = 词元指纹 + 锚点 Jaccard（而非向量库/LLM 直判）
**依据**: 跨源实测（92 条 → 4 个多来源簇，0.001s）证明确定性方法有效；Pharos 的指纹设计 + Heatwire 的窗口/seed-guard 是可移植的纯 SQL/Python 算法；LLM 直判（news-aggregator 模式）非确定性且贵，仅留作灰区仲裁。
**灰区**: Jaccard 0.25-0.30 之间的归并交 LLM 仲裁（可选，未来开）。

## D6. 图片 = 自写元数据优先提取器（而非通用爬图）
**依据**: 生态共识（PicoNewsAgent/finviz）+ 实测（BBC 5/5 主图命中）；og:image→twitter→JSON-LD→srcset 评分过滤，cap 8MB，content-hash 去重。pHash 暂不引入。

## D7. 调度 = cron one-shot（而非常驻进程/APScheduler/Celery）
**依据**: 20 进程上限 + 512MB；原型全串行 11.4s/5 篇证明 one-shot 形态可行；10-15 分钟间隔足够新闻时效；MuckScraper APScheduler 常驻形态被否。

## D8. AI = 外部 OpenAI-compatible API + 分层熔断
**依据**: 无本地模型资源；Heatwire 的 tiered LLM + 3 连败熔断 + MuckScraper 的 hosted 模式；AI 失败不阻塞数据入库。
**接口**: env.local 提供 OPENAI_BASE_URL/KEY；兼容 DeepSeek/Qwen/Gemini(openai 兼容端点)。

## D9. Web = 后置（阶段4），轻量优先
**决定**: 先采集后阅读；Web 候选：静态生成/SQLite+FastAPI 单进程（受 20 进程约束），绝不上 Next.js 常驻 SSR。

## D10. 网站适配器 = sites/ 目录 + 通用规则兜底 + 自适应学习
**依据**: ftr-site-config 的"通用优先、逐站兜底"成熟范式 + Scrapling 自适应实测 + Evening News 的模式晋升表思想（简化版：per-domain 选择器成功率计数，失败降级通用提取）。

## 被否组件清单（一票否决原因）
| 组件 | 原因 |
|---|---|
| PostgreSQL/pgvector/Meilisearch/Redis | 无必要 + RAM/进程 |
| Ollama / 本地 LLM | 内存超出 2 个数量级 |
| Playwright/Chromium/Camoufox | FreeBSD 无支持（证据 D3） |
| Docker / docker-compose | 无 root |
| Next.js 常驻 SSR | 常驻进程 + 资源 |
| Celery/RQ/消息队列 | 单机 cron 足够 |
| Scrapy 框架 | 重（Twisted 常驻式架构），我们用简单函数管道 |
| news-please | 依赖 Scrapy 生态，同样偏重 |
| morss（直接复用） | AGPL 传染；仅借其"自写轻量解析"思路 |
