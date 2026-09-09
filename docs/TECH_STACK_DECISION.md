# TECH_STACK_DECISION — 最终技术栈决策

> 日期: 2026-09-09 · 全部经过 Serve00 (FreeBSD/512MB/20进程) 实测或上游证据排除
> 决策详据见 SCRAPER_DECISIONS.md (D1-D10)；性能数据见 SCRAPER_BENCHMARK.md

## 推荐栈一览

```
Serve00 (FreeBSD, 512MB, 20 proc, no-root)
│
├── RSS/发现层      feedparser 6.0.11（系统预装）+ 条件GET + 源健康表
├── HTTP 抓取层     httpx 0.28.1（预装）· UA 合规 · 超时 20s · 重试 3 次退避
├── 解析/自适应层    Scrapling 0.4.15 解析层（Selector/markdown/save-relocate）
├── 正文提取层       trafilatura 2.2.0（主力）→ Scrapling p-text → RSS 摘要
├── 图片层          自写提取器（og/twitter/JSON-LD/srcset 评分）+ httpx 下载 ≤8MB
├── 去重层          URL 规范化 + sha256 + 标题 Jaccard≥0.8
├── Story 聚类      词元指纹 + 锚点 Jaccard ≥0.30 + ±72h 窗（实测 0.001s/92条）
├── AI 层          外部 OpenAI-compatible API（DeepSeek/Qwen/Gemini 可换）+ 熔断
├── 数据库          SQLite（WAL + FTS5）· 平台 ZFS 每日快照兜底
├── 调度            系统 cron（one-shot，10-15 分钟，串行 ≤20 篇/轮）
├── Web            阶段4：FastAPI 单进程或静态生成（待定，受 20 进程约束）
└── 初始化          serve00-init.sh v1.0.1（manifest 幂等回滚）
```

**依赖总量**: venv 内新增 8 个包（scrapling/trafilatura/orjson/cssselect/tld/w3lib/markdownify/lxml 升级），无浏览器、无数据库服务、无消息队列。

## 分层"为什么"速查

| 层 | 选择 | 为什么（一句话） | 为什么不是别人 |
|---|---|---|---|
| RSS | feedparser | 预装、标准、条件 GET | news-aggregator 的 fast-xml-parser 是 Node 侧方案 |
| HTTP | httpx | FreeBSD 零障碍、http2、超时/重试可控 | **curl_cffi 上游拒绝 FreeBSD（实测）**；requests 无 http2 |
| 正文 | trafilatura | 新闻站专业提取+元数据 JSON，实测 BBC 成功 | readability-lxml 精度略逊；Scrapling markdown 依赖 Response(需 Fetcher) |
| JS 站点 | 站点规则 → 外部渲染 → 放弃 | **Crawl4AI/Playwright 在 FreeBSD versions:none（实测）** | 本机浏览器方案全部出局 |
| 图片 | 自写评分提取器 | og 优先+关键词过滤实测 5/5 命中 | 通用库（如 img2dataset）过重 |
| 去重 | canonical+sha256+Jaccard | 确定性、零依赖 | SimHash（Pharos）留作正文近似去重升级位 |
| Story | 指纹+锚点Jaccard+窗口 | 实测 92→19 簇/0.001s，可解释 | pgvector/HNSW（无 PG）；LLM 直判（非确定性+贵） |
| AI | OpenAI-compatible 远端 | 零本地资源；Heatwire 熔断模式 | Ollama（内存超 2 个数量级）；Copilot SDK（绑定+子进程） |
| DB | SQLite WAL+FTS5 | 四个参照项目同规模验证；实测建表通过 | MySQL/PG 无 pgvector 且无必要 |
| 调度 | cron one-shot | 原型 11.4s/5篇；不占常驻进程 | APScheduler 常驻（MuckScraper）、systemd（无） |
| Web | （阶段4定）FastAPI/静态 | 20 进程红线 | Next.js SSR（常驻）；FreshRSS（PHP 常驻+重） |
| 反馈学习 | votes 表→few-shot 注入 | Beehive MIT 模式：40 行 SQL+1 段 prompt，即时生效 | Cruxwire 嵌入味心（需 embeddings）；EveningNews（PG+无license） |
| 初始化 | serve00-init.sh v1.0.1 | 实测幂等/dry-run/doctor/manifest 回滚 | 裸脚本/Ansible（过重） |

## 为什么没用这些项目（用户点名的必答项）

- **MuckScraper(-v2)**：设计最优（Story/Edition 模型），但栈是 PG+pgvector+Meilisearch+Ollama+Chromium+Docker——在 512MB/20 进程/无 root 上每项都超标。→ **借设计**（三级聚类级联、遥测/冷却/黑名单、edition 工作流）。
- **Heatwire**：AI 全托管化（好榜样），但 Next.js 常驻 + PG。→ **借设计**（heat 公式、72h+seed-guard 聚类、源自动停用）。
- **Pharos**：SQLite 路线的最佳证明，但 LICENSE 专有（禁止复制代码）+ FastAPI 常驻。→ **只借设计**（指纹/锚点 Jaccard、状态列队列、SimHash）。
- **FreshRSS**：PHP 常驻多进程 + MySQL，是"RSS 阅读器"不是"研究资料库"，且不符合无 Story/无 AI 管线需求。→ 放弃。
- **Cruxwire**：零依赖可敬，但 Ollama 绑定 + JSON 存储。→ 借（兴趣公式）。
- **Beehive**：Python 3.12 + Copilot SDK。→ 借（votes→few-shot 环，MIT 可复用实现）。
- **Evening News**：无 license + PG + Chrome。→ 借（纠正映射、抓取模式晋升）。
- **news-aggregator**：最接近可部署（MIT/1依赖/Node 22.22.2 兼容），但无正文/图片抓取，聚类靠 LLM 非确定。→ 作为 cron 形态与"空结果不保存"参照；不直接部署。
- **Crawl4AI**：FreeBSD 无法安装（证据链）。→ 本机放弃；未来外部渲染服务的候选。
- **Scrapling**：**采用（解析/自适应层）**；其 Fetcher/浏览器层因 curl_cffi 拒绝 FreeBSD + playwright 无 wheel 而弃用。

## 资源占用预算（实测推算）

| 项 | 预算 | 实测 |
|---|---|---|
| 每轮 cron（20 篇批） | <2 min, <150MB | 5 篇全链 11.4s / 87MB（含图片下载） |
| SQLite 增长 | ~50KB/篇(含正文) | 3GB 磁盘 ≈ 数年文字量；图片 8MB 封顶+清理任务 |
| 内存峰值 | <150MB | 87–105MB |
| 进程 | 1（one-shot） | 1 |
| AI 调用 | 仅新 story/批处理 | 熔断保护 |

## 长期维护方式

1. serve00-init.sh 定期 `doctor`（阈值告警）
2. `sources` 表健康度 + crawl_errors 周报（人工审）
3. `pip freeze` 锁版本；升级先在 news-lab 验证再进生产 venv
4. 平台 ZFS 快照 + 手动 `~/news-backups/` 数据库 dump 周备
5. 网站 HTML 快照样本进 `news-lab/fixtures/` 供提取回归测试
