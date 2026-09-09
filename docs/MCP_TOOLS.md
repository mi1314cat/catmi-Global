# MCP_TOOLS — MCP 工具全集（12 只读工具, 2026-09-09 v2）

> 端点: `https://<你的域名>/mcp` · 协议: Streamable HTTP（2025-06-18 现役形态, 无状态 + JSON 响应）
> 认证: Bearer 必需（env.local 的 MCP_TOKEN, chmod 600）· 限速 60 req/min/IP · body ≤256KB · 全部工具只读
> 配置样例:
> ```json
> {"mcpServers": {"global-intelligence": {"url": "https://<你的域名>/mcp",
>   "headers": {"Authorization": "Bearer <MCP_TOKEN>"}}}}
> ```

## 三能力分区

### A. Web Search（搜索互联网——不是搜我们的库）
| 工具 | 参数 | 说明 |
|---|---|---|
| **web_search** | q(必), time_range(day/week/month/year), language, region, category(general/news), limit≤20, page | 5 个 keyless provider 并发 + 可插拔 SearXNG PRIMARY；返回 results[{title,url,snippet,source,published,provider}] + providers[{status,latency_ms,count/error}]；跨源去重；任一 provider 挂不影响整体 |
| **deep_search** | q(必), time_range, language, category, max_pages≤3, budget_ms≤60000 | 多步研究编排（无 AI）: web_search → 去重/每域 1 条 → read_url 前 N 页（预算内）→ 情报库关联 → {sources_picked, pages[{status,excerpt,…}], intelligence_matches{articles,stories}, steps} |

### B. URL Reader（读取搜索到的网页）
| 工具 | 参数 | 说明 |
|---|---|---|
| **read_url** | url(必), timeout_ms≤45000 | 复用管道提取栈（trafilatura→Scrapling）；返回 {title, author, published, source, content, content_chars, images[], language, canonical_url, method}；**状态语义**: ok / inaccessible（401/403/429——不绕过）/ needs_js（动态页, Crawl4AI 默认关）/ failed；并发上限 2 子进程 |

### C. Intelligence Search（本地情报库——Collector 持续采集的成果）
| 工具 | 参数 | 说明 |
|---|---|---|
| **search_intelligence** | q(必), hours, category, language, sort, limit, offset | 文章 FTS5 全文检索 + Story 事件簇合并返回 |
| **search_news** | 同上（无 stories） | 纯文章检索（BM25 相关性 / recent 时间序） |
| **search_events** | q, hours, category, limit, offset | 事件簇检索（跨源归并的 Story） |
| **get_event** | id | 事件全部来源文章 + timeline + 计数 |
| **get_timeline** | id | 按发布时间的事件时间线 |
| **get_article** | id | 单篇全文（72h 窗内）+ 图片元数据 |
| **search_media** | q, hours, limit | 视频/媒体热点（YouTube/B站/Vimeo 元数据; 含 story 关联） |
| **get_trending** | hours, category, limit | 热点榜（heat = Σ 独立源×时间衰减） |
| **list_sources** | — | 52 源注册表（kind/类别/语言/24h 产量/失败率/状态） |

## 安全边界（全部实测）
- Bearer 错 token/无认证 → **401**（10/10 实测）+ WWW-Authenticate
- Origin 非白名单 → **403**；Host 校验（DNS 重绑定防护）
- 限速 60 req/min/IP → 429；body >256KB → 413
- zod schema 输入校验（工具参数非法 → -32602）
- **工具面纯只读**: 无 shell/exec/delete/install/filesystem write/database write
- 请求日志脱敏（无 Authorization/query/body）; >5MB 轮转

## Agent 场景 → 工具映射（§四十三 验收用例）
| 场景 | 调用 |
|---|---|
| 实时搜索"最近 24h DeepSeek 新闻" | web_search{q:"DeepSeek", time_range:"day", category:"news"} |
| 全球多语言报道 | web_search{q, language:"zh"/"ja"…}（gnews 路线实测中文可用） |
| 事件研究"过去三天变化" | get_event / get_timeline + search_events{hours:72} |
| 交叉验证 ≥5 来源 | deep_search（每域 1 条选多源 + read_url）或 web_search{limit:10} |
| 读取网页 | read_url{url} |
| 历史搜索 | search_intelligence{q, hours:720} |
| 混合研究 | deep_search（自动 web+读页+库关联） |

## 已验证的 Agent 模拟记录（生产 MCP, 真实数据）
- web_search "Nvidia earnings"(news/week): gnews+bingnews ok, 返回真实新闻 URL; provider 状态可见
- read_url bbc.com/news: 6921 字符/2.0s/trafilatura
- deep_search "UK West Bank sanctions": 读页 1468 字符 + 情报库 9 篇/58 事件匹配, 2.3s
- search_intelligence "tariff"/72h: 6 篇 + 2 事件
- 初始化握手 2025-06-18 ✓；tools/list 12 工具 ✓；错 token 401 ✓
