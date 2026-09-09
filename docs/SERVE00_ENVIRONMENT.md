# SERVE00_ENVIRONMENT — Phase 0 环境实测报告

> 检测时间: 2026-09-09 03:09 UTC（服务器实测脚本 `news-lab/envcheck.sh`，原始输出 `news-lab/results/envcheck.out`）
> 原则: 全部为实测值，非文档转述；秘密零包含。

## 1. 主机与配额（实测 `devil info limits`）

| 项 | 实测值 |
|---|---|
| 系统 | FreeBSD s12.serv00.com 14.3-RELEASE-p18 amd64（内核编译 2026-09-02） |
| 主机运行 | up 6 days，load 3.43-4.50（共享负载中等） |
| 磁盘配额 | **52.5M / 3.0G（1.71%）** |
| 进程 | 7/20（35%） |
| 内存 | 116M / 512M（22.65%） |
| CPU | 0.1% |
| PHP worker | 0/3 ×各版本（本项目不用 PHP） |
| MySQL/PG/Mongo | 0（均未申请，本项目不需要） |
| 预留端口 | 0 |
| ulimit | maxuserproc=20、openfiles=1500、datasize=32MB?（实为 33554432KB=32GB 虚拟上限）、stack 512MB |

> 注意: `ulimit -m` 显示 2048000KB=2GB，但**账户配额硬限制是 devil 的 512M**——以 devil 为准。

## 2. 运行时

| 组件 | 版本 | 备注 |
|---|---|---|
| Python | 3.11.13（系统） | 系统预装 feedparser 6.0.11 / httpx 0.28.1 / lxml 5.4.0 |
| SQLite（Python 模块 + CLI） | **3.50.2** | **FTS5 实测可用** ✅ |
| Node.js | v22.22.2 | **node:sqlite（DatabaseSync）实测可用** ✅ |
| npm | 11.14.1 | registry.npmjs.org 可达（200） |
| 编译工具链 | clang 19 / rustc 1.95（Phase 2 实测） | 可编译 lxml/orjson 等源码扩展 |

## 3. Web / 域名 / 进程模型

| 项 | 实测 |
|---|---|
| 域名 | <你的域名>（nodejs 类型，Passenger） |
| 目录 | /usr/home/catmi/domains/<你的域名>（入口 public_nodejs/app.js） |
| HTTPS | **200（0.32s）**，Cloudflare 代理，源站证书至 2041（**不动**） |
| 应用生命周期 | Passenger 按需拉起/回收；重启后首个请求自动复活（满足"可恢复"） |
| 端口 | 无预留（Passenger 注入 PORT env） |

## 4. 网络出口实测（GET + 描述性 UA）

| 端点 | 状态 | 结论 |
|---|---|---|
| feeds.bbci.co.uk/news/world/rss.xml | 200 | ✅ |
| text.npr.org | 200 | ✅ |
| news.google.com/rss | 200 | ✅（发现渠道可用） |
| hn.algolia.com/api/v1/search | 200 | ✅ |
| reddit.com/r/worldnews/.rss | 200 | ✅（需低频+礼貌 UA） |
| bing.com/news/search?format=rss | 200 | ✅ |
| api.gdeltproject.org（doc API） | **000 超时** | ⚠️ 连接失败（复测一次仍 000）→ 列为"受限源"，设计降级（重试+可选代理/禁用） |
| youtube.com/feeds/videos.xml?channel_id=UC16niRr50... | 404 | 频道 ID 错误（API 本身正常），需正确 ID |
| rsshub.app | 403 | 公共实例 Cloudflare 拦截 → 不可靠，降级/放弃自建（Redis+Puppeteer 超资源） |
| registry.npmjs.org | 200 | ✅ npm 可用 |

## 5. MCP 关键预检（决定 Phase 5 技术路线）

- `npm install @modelcontextprotocol/sdk` 在本机**成功**（node_modules 仅 **2.0M**）
- `import {McpServer} from '@modelcontextprotocol/sdk/server/mcp.js'` ✅
- `import {StreamableHTTPServerTransport} from '.../streamableHttp.js'` ✅
- **结论: MCP 走官方 TS SDK（Streamable HTTP）+ Passenger Node 常驻按需进程**，无需手写协议层

## 6. 现有目录与占用

```
~/news-project/  18M  （serve00-init.sh + 11 份文档 + venv + news-data/ + sites/ + sources.seed.json + news/ 包）
~/news-lab/      34M  （实验室 venv + 8 测试脚本 + results/ 原始证据）
~/backup/        479K （nav-item 备份，保护不动）
~/domains/       24K  （占位站点）
家目录合计 ~53M / 3.0G
```

## 7. 对架构的约束（写进 ARCHITECTURE.md）

1. **20 进程上限** → cron one-shot 串行管道；Passenger Node 常驻 ≤1 进程（按需）+ 管道进程瞬时 ≤2
2. **512MB** → 单批条目数受限（SCAN_BATCH=10 源/FETCH_BATCH=12 篇/轮），实测峰值 <110MB
3. **FTS5 可用** → 全文检索走 SQLite FTS5（无 ES/Meilisearch）
4. **MCP SDK 可用** → Phase 5 直接用官方 SDK
5. **GDELT 出口受限** → 热点发现主渠道 = RSS + Google News RSS + Bing News RSS + HN/Reddit；GDELT 作为可选增强（失败自动禁用）
6. **rsshub 公共实例不可靠** → 数据源策略里 RSSHub 仅作为"最后手段"，优先官方 RSS/API/sitemap
7. 磁盘保护基准: 配额 3GB，阈值 50%/70%/85%（warn/high/emergency）
