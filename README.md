# Global Intelligence

> 全球热点事件情报 + Agent Web Search 基础设施（自托管，个人可跑，AI 可选）

一个跑在**免费共享主机**（Serv00/FreeBSD 512MB 级）上的全球热点情报系统：
持续采集 52 个新闻源 → 正文/图片提取 → 去重 → 事件聚类 → SQLite(FTS5) → REST API + MCP 服务器 + 中文 Web 控制台。

## 三大能力（Agent 视角）
| 能力 | 说明 | 零依赖 |
|---|---|---|
| **Web Search** | 搜索实时互联网：Google News RSS / Bing News / Bing / DDG / Wikipedia 并发查询 + 逐后端状态记录（MCP: `web_search`, `deep_search`） | ✅ 零 API Key |
| **Intelligence Search** | 搜索自己采集的情报库（文章 BM25 + 事件簇） | ✅ |
| **URL Reader** | 读取任意网页（trafilatura→Scrapling 三级提取，SSRF 全防护，不绕过访问控制） | ✅ |

- MCP 12 只读工具（Streamable HTTP + Bearer + 可撤销 Token）
- 登录系统（scrypt + 会话 + CSRF + admin/user 权限）
- 管理后台 14 页（MCP Token 管理/来源管理/用户/日志/16 项系统诊断）
- 采集：rss/sitemap/api/gnews 四类适配器，事件聚类（锚点包含+标题 Jaccard），72h 原文滚动 + 磁盘四级保护
- **AI 完全可选**：全部 LLM 关闭时系统完整可用（deep_search 为确定性编排）

## 快速开始（简述）
```
Python 3.11（venv: httpx/trafilatura/scrapling/feedparser…）
Node 22（零 npm 依赖，仅 @modelcontextprotocol/sdk 用于 MCP）
SQLite ≥3.45（FTS5）
```
- `news/` — 采集管道（python -m news.newsctl run 等）
- `web/` — Node 服务（REST + MCP + 静态控制台）
- `web/lib/websearch.js` — 网络搜索 provider 层（可插拔 SearXNG）
- `docs/` — 全部设计与运维文档

## 安全
密码 scrypt 哈希 / Token 仅哈希入库 / 会话 HttpOnly+Secure / CSRF / 登录限速 / SSRF 防护 / MCP 只读。
秘密一律走 `env.local`（600），模板见 `env.local.example`。

## License
MIT
