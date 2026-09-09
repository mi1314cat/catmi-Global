# PROJECT — Serve00 全球热点情报采集 + 搜索 + MCP Agent 工具服务器

> 最终定位: **个人全球热点情报数据库 + 搜索引擎 + Agent MCP 工具**
> 我的 Agent 负责: 理解/分析/写作/推理。本系统负责: 发现→抓取→整理→保存→搜索→提供工具接口。
> 域名: https://<你的域名>（SSL 不动）· 主机: s12.serv00.com（FreeBSD/512MB/20 进程）

## 核心原则（不可妥协）

1. **AI 绝不是核心依赖**——全部 AI 关闭后: 采集✓ 存储✓ 去重✓ Story✓ 搜索✓ API✓ MCP✓
2. MCP（Streamable HTTP）与 REST 是 Agent 的主要接口；Agent 不该重新上网找新闻
3. 覆盖: 全球媒体/科技/财经/地缘政治/社会/视频热点（视频只存元数据）
4. 存储 72h 滚动 + 磁盘保护水位；不做"新闻门户"，做"资料库+工具"
5. 反 Frankenstein：Python 管道 + Node 服务 + SQLite，**没有** PG/Redis/ES/Meilisearch/Ollama/Chromium/Docker

## 阶段进度

| Phase | 内容 | 状态 |
|---|---|---|
| 0 | 环境实测 SERVE00_ENVIRONMENT.md | ✅ 2026-09-09（FTS5✓/node:sqlite✓/MCP SDK✓/GDELT 受限/rsshub 403） |
| 1 | RSS Collector + 队列 + SQLite + 基础搜索 | ✅ 实测: 31 源种子, 375 文章, 0 错误 |
| 2 | Scrapling + 正文/图片提取 | ✅ 实测: trafilatura 30s/25 篇全提取, canonical/hash 去重, 图片 10/10 |
| 3 | 去重 + Story 聚类 + Trending | ✅ 实测: 聚类 v2 锚点归并 52-74/300 批次, heat/trending 248 事件 |
| 4 | REST API（Node/Passenger 分页） | ✅ 上线: 8 端点全实测 200（/api/health news stories trending sources images） |
| 5 | MCP Server（Streamable HTTP + Bearer + 只读工具） | ✅ 上线: SDK 1.30 无状态 JSON 模式, 8 工具实测（initialize/tools/list/tools/call, 401 保护）, 生产 cron 已装 |
| 6 | Crawl4AI fallback | ✅（Phase 2 研究已证本机不可行→外部渲染钩子, 默认关） |
| 7 | Web UI + 72h Cleanup + 磁盘保护 + 监控 | 🔄 剩余: Web UI 前端 + 监控页（retention/磁盘门/cron 已落地） |
| 8 | 压力测试 + TEST_REPORT.md | ⬜ |

## 文档体系（全部秘密零包含）

| 文档 | 内容 | 状态 |
|---|---|---|
| PROJECT.md | 本文档 | ✅ |
| ARCHITECTURE.md | 双进程架构/数据流/AI原则/服务层 | ✅ |
| SERVE00_ENVIRONMENT.md | Phase 0 实测 | ✅ 完成|
| SOURCE_STRATEGY.md | 数据源分层策略+验证清单 | 🔄（子代理研究中） |
| SCRAPER_RESEARCH.md / SCRAPER_BENCHMARK.md / SCRAPER_DECISIONS.md | 采集引擎研究（Phase 2 遗产） | ✅ |
| GITHUB_PROJECT_RESEARCH.md / GITHUB_LICENSES.md / TECH_STACK_DECISION.md | OSS 研究 | ✅（增量核查中） |
| DATABASE_DESIGN.md | 表结构/索引/FTS5/保留联动 | 🔄 |
| STORY_CLUSTERING.md | 聚类算法/参数/可解释性 | 🔄 |
| API.md | REST 端点规范 | ⬜ |
| MCP.md | MCP 工具/协议细节/安全 | 🔄（子代理研究中） |
| STORAGE_POLICY.md | 72h 滚动/水位/降级矩阵 | ⬜（retention.py 已实现） |
| SECURITY.md | 认证/限速/日志/红线 | ⬜ |
| DEPLOYMENT.md | 部署/cron/备份/恢复 | ⬜ |
| CHANGELOG.md | 变更记录 | 🔄 |
| TEST_REPORT.md | 阶段实测+压测 | 🔄（每阶段追加） |

## 代码地图

```
本地 serve00-catmi/                服务器 ~/news-project/
├── news/  (Python 管道包)    →    news/            （cron 用）
│   ├── newsctl.py CLI             ├── venv/（含 scrapling/trafilatura 全家）
│   ├── collector.py 扫描          ├── sources.seed.json（31 源种子）
│   ├── extractor.py 正文           ├── news-data/{database,images,cache,logs}
│   ├── images.py 主图              └── serve00-init.sh（初始化/自检）
│   ├── stories.py 聚类
│   ├── trending.py 热度       →    ~/domains/.../public_nodejs/（Phase 4-5: app.js + api/ + mcp/ + public/）
│   ├── retention.py 保留
│   ├── fetcher.py HTTP 层
│   ├── search.py 检索
│   ├── sourcesvc.py 源注册
│   └── db.py config.py schema.sql
├── news-lab/ (实验室+证据)
└── *.md (文档体系)
```

## cron 计划（Phase 7 定稿）

```
*/10 * * * *  run      # 主管道（scan 分片→fetch→images→cluster→trending）
35 * * * *    cleanup  # 每小时轻清理（缓存过期）
05 04 * * *   cleanup  # 每日全清理（72h 滚动+归档）
10 04 * * *   backup   # 每日备份（保留 7 份 gz）
20 04 * * *   doctor   # 每日自检
```
