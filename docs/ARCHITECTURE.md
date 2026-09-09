# ARCHITECTURE — 全球热点情报采集 + 搜索 + MCP Agent 工具服务器

> 状态: v1（Phase 1-3 实现后定稿）· 环境: SERVE00_ENVIRONMENT.md · 决策依据: SCRAPER_RESEARCH/DECISIONS + TECH_STACK_DECISION
> 定位: 个人的全球热点情报数据库 + 搜索引擎 + Agent MCP 工具。**AI 绝不进核心链路。**

## 1. 双进程架构（共享单库 SQLite）

```
        ┌── cron (5-15min, one-shot) ──┐        ┌── Passenger (按需常驻) ──┐
        │  Python 采集管道 (one-shot)    │        │  Node 22 服务层           │
        │  ~/news-project/news/        │        │  public_nodejs/app.js    │
        │  scan→fetch→images→          │  WAL   │  REST API /api/*         │
        │  cluster→trending            │ ─────▶ │  MCP  /mcp (Streamable)  │
        │  cleanup(每日) backup(每日)    │  读写   │  Web UI /  (管理+检索)    │
        └──────────────┬───────────────┘        └────────────┬─────────────┘
                       │      ~/news-project/news-data/      │
                       │        database/news.db (WAL+FTS5)  │
                       │        images/YYYY-MM/  cache/      │
                       ▼                                     ▼
                  https://<你的域名>  （域名+SSL 不动）
```

**为什么 Python 采集 + Node 服务**：
- 采集管道 = 重 IO 批处理，cron one-shot 退出（不占 20 进程配额）；Python 生态（feedparser/trafilatura/Scrapling）实测最优
- 服务层 = 需要常驻按需响应（Passenger 模型），Node 22 内置 node:sqlite 直接读同一 WAL 库；官方 MCP TS SDK 实测可装（2MB）
- 单库共享: WAL 模式允许多读单写，采集写 / 服务读互不阻塞

## 2. 数据流（核心链路，全部确定性，AI 可选增强）

```
Source Registry(sources 表 + sources.seed.json)
  → SCAN: 到期源扫描(feedparser, 条件GET, 礼貌延迟1.2s/域, 403/429/5xx退避)
    → articles(status=discovered) + crawl_tasks(article)
  → FETCH+EXTRACT: httpx 抓取(20s超时, 3次退避) → trafilatura JSON(元数据)
      → 兜底: Scrapling CSS p-text → RSS 摘要(标记降级)
      → canonical/OG url 解析, content_hash, 结构有效性校验(≥200字符+标题)
      → Article Dedup: canonical 精确 / content_hash 精确 → status=dupe(dupe_of 指向保留篇)
      → 原始页面 gz 缓存(72h)
  → IMAGES: og:image→twitter→JSON-LD→srcset 评分 → HEAD 预检 → ≤8MB 下载 → sha256 去重
      → 磁盘水位 high/emergency 自动跳过
  → CLUSTER (Phase 3): 词元指纹(t:标题/d:域/w:正文) + 锚点Jaccard≥0.30 + ±72h窗
      → Story #N: 保留全部来源, article/source/video 计数, 时间线
  → TRENDING (Phase 3): heat = Σ_独立源 best(priority × exp(−age_h/30h))
      → importance: ≥6 major / ≥3 high / ≥1.2 normal
  → RETENTION (每日): 正文+图片 72h 置 purged / 元数据 30d / story 归档 90d / 缓存 24h
```

## 3. AI 原则（可插拔 Provider）

- 核心链路（发现→抓取→提取→去重→聚类→搜索→API→MCP）**零 AI 依赖**
- `news/ai/`（Phase 5+ 可选）: OpenAI-compatible Provider，env.local 提供 AI_BASE_URL/AI_API_KEY；无 key = 全部跳过
- 增强点: story 摘要润色 / 实体补全 / 灰区聚类仲裁 / 分类精修——均为**旁路写入**，原文永不覆盖
- votes→few-shot 反馈环（Beehive 模式）同理可选

## 4. 服务层（Phase 4-5-7）

| 能力 | 实现 | 认证 |
|---|---|---|
| REST API `/api/*` | Node + node:sqlite, 分页(≤50/页), 只读 | 公开读(可后续加 token) |
| MCP `/mcp` | 官方 TS SDK StreamableHTTPServerTransport | **Bearer Token 必需**（env.local MCP_TOKEN）+ Origin 校验 + 限速 + 日志 |
| Web UI `/` | 静态资产 + 少量 JSON 端点（管理+检索，非门户） | 公开读；管理操作仅本地 CLI |
| 工具 | search_news / search_events / get_event / get_article / get_trending / search_media / get_timeline / list_sources —— 全部只读 | 禁止 shell/exec/delete/write |

## 5. 存储与磁盘保护（详见 STORAGE_POLICY.md）

| 层 | 数据 | 生命周期 |
|---|---|---|
| 短期 | 正文/图片/原始缓存/完整抓取 | **72h**（可配） |
| 中期 | URL/标题/来源/作者/Story 关联/标签 | 30d（可配） |
| 长期 | Story/时间线/重大事件/收藏 | 90d+（可配） |

磁盘水位（du 家目录 vs 3GB 配额）: normal(<50%) → warn(≥50% 停图片下载新请求) → high(≥70% 清过期+停图) → emergency(≥85% 仅元数据模式, 管道跳过抓取只清缓存)。**任何水位都不崩库**（SQLite+WAL+阈值联动）。

## 6. 安全（详见 SECURITY.md）

- MCP_TOKEN 只存 env.local（chmod 600）；不入 Git/日志/文档
- 采集: 合规 UA、robots 尊重、不绕过任何访问控制、403/429 退避、每域延迟
- 服务: 分页上限、输入参数化（SQLite 占位符全用）、错误日志脱敏
- 数据: 家目录外无写入；备份仅含 db gz（无密钥文件）

## 7. 故障恢复

- Passenger 重启 → 服务层自动按需复活（实测行为）
- 管道崩溃 → cron 下轮继续；crawl_tasks 状态机支持断点（running 超 1h 视为 stuck 可重跑）
- 数据库损坏 → doctor PRAGMA quick_check + 每日 backup（保留 7 份 gz）

---

# v2 增补（2026-09-09 Global Intelligence 升级）

## 三能力架构（SEARCH_ARCHITECTURE.md 详述）
```
Agent ──MCP(12 tools)──┐
REST ──/api/*──────────┼──> Unified Query Service (lib/query.js)
Web Console ───────────┘           │
                    ┌──────────────┼────────────────┐
                    ▼              ▼                ▼
              Web Search    Intelligence Search   URL Reader
              (websearch.js) (newsdb.js→SQLite)   (reader.js→python)
                    │                                │
        5 keyless providers                  trafilatura→Scrapling
        (+SEARXNG_URL 可插拔 PRIMARY)          (状态: ok/inaccessible/needs_js)
```
- 采集管道（Collector）不变: 持续发现/提取/聚类入库 = Intelligence 层的"历史"
- Web Search = "现在"; Intelligence = "历史"; read_url = "深入" —— 三者经 MCP 统一暴露
- deep_search = 三者的确定性编排（无 AI, 预算控制）

---

# v3 增补（2026-09-09 第二阶段产品化）

## 认证层（新增）
```
浏览器 ──Cookie(gi_session)──> app.js 认证门禁
        │                        ├─ /api/auth/*（公开: login/logout/me）
        │                        ├─ /api/admin/*（admin 会话 + CSRF 头 + 写审计）
        │                        ├─ /api/...（公开只读, 限速）
        │                        └─ 静态/登录页
Agent ──Bearer──> /mcp ──> env token OR auth.db token（哈希, 可撤销, 调用统计）
存储: auth.db（users/sessions/mcp_tokens/audit_log, Node 可写）
      news.db（管道独占写 + 管理面 sources 运营写, busy_timeout=5000）
```
## 诊断与安全
- read_url: SSRF 全护（私网/本地/metadata/非 http 拒绝）+ Content-Type 白名单 + 5MB 上限
- 诊断: /api/admin/diagnostics 16 项真实检查 + 可复制报告; MCP 自测 9 项
