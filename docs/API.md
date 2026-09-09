# API.md — REST API（Phase 4, 已上线）

> 基址: `https://<你的域名>/api/` · 零框架 Node 22 · 只读 SQLite（与采集管道共享 WAL 库）
> 限速: 120 req/min/IP → 429 · 日志: news-data/logs/web.log（脱敏）· 无认证（公开读, 与 MCP 认证化双轨）

## 端点一览（8 个, 全部已实测 200）

| 端点 | 参数 | 说明 |
|---|---|---|
| GET /api/health | — | 系统健康: 文章/事件/图片/源/任务/错误计数 + last_run |
| GET /api/news | q?, hours?, category?, source?, language?, sort(relevance\|recent), limit≤50, offset | 全文检索（FTS5 BM25 + LIKE 兜底）, 返回 {total,limit,offset,results[]} |
| GET /api/news/latest | hours?, category?, limit, offset, include_purged=1 | 最新文章流（默认排除 purged） |
| GET /api/news/:id | — | 单篇详情: 全文(72h 窗)/作者/canonical/图片/所属事件 |
| GET /api/stories | q?, hours?, category?, limit, offset | 事件簇检索（stories_fts, 附每簇 6 篇代表文） |
| GET /api/stories/:id | — | 事件详情: 全部来源文章 + timeline[]（按时间） |
| GET /api/trending | hours=24, category?, limit≤50 | 热点榜（heat 降序, importance 标注） |
| GET /api/sources | — | 源注册表（52 源, kind/健康/计数） |
| GET /api/categories | — | 类别计数 |
| GET /api/images/:id | — | 图片二进制（72h 窗内本地文件; 路径遍历防护） |

## 响应约定
- 列表: `{total, limit, offset, results[]}` — 客户端翻页 offset += limit
- 错误: JSON `{error}` + 404/429/413/405；未知端点附 hint
- 时间: ISO-8601 UTC（"2026-09-09T03:53:37Z"）
- FTS snippet: BM25 命中片段（`[..]` 高亮标记）

## MCP（同库双轨, 见 MCP.md）
`POST /mcp` + Bearer token — 8 个只读工具与 REST 同语义（search_news/search_events/get_event/get_article/get_trending/search_media/get_timeline/list_sources）。
