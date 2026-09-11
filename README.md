# Global Intelligence

> 全球热点事件情报 + Agent 实时搜索基础设施（自托管，免费共享主机可跑，AI 可选）

一个跑在**免费共享主机**（Serv00 / FreeBSD 512MB 级）上的全球热点情报系统：
持续采集 100+ 新闻源 → 正文/图片提取 → 去重 → 事件聚类（独立源计数 + fact_status）→ SQLite(FTS5)
→ REST API + MCP 服务器（12 只读工具）+ 中文 Web 控制台。

## 能力一览

| 能力 | 说明 | 零依赖 |
|---|---|---|
| **实时搜索** (`web_search` / MCP) | Google News RSS / Bing News / Bing / DDG / Wikipedia 并发查询，逐后端健康状态，UA 反爬对策内置 | ✅ 无 API Key |
| **深度研究** (`deep_search` / MCP) | 搜索→选页→读页→补漏的确定性多轮编排（LLM 可选加速） | ✅ |
| **情报检索** (`search_intelligence` 等) | 自建库文章 BM25/FTS5 + 聚类事件 + 独立源计数 + fact_status + 时间线 | ✅ |
| **URL 读取** (`read_url` / MCP) | trafilatura→Scrapling 三级提取，SSRF 全防护，诚实失败状态（paywall/bot_protection 不会骗你） | ✅ |

- **MCP**：Streamable HTTP + Bearer；token 可撤销、**可按工具分权**（`*` 全部 / 后台勾选白名单）
- **REST API**：公开读端点可按**端点独立开关 + 独立限流**控制（管理后台勾选式设置）
- **限流**：登录用户豁免；匿名按端点/全局计数，上限自动钳制（端点≤60/min，MCP≤120/min，公开API≤300/min）
- **安全**：scrypt + 会话（HttpOnly/Secure/SameSite）+ CSRF（403 自动刷新重试）+ 登录限速 + Token 仅存哈希
- **AI 完全可选**：全部 LLM 关闭时系统完整可用

```
news/               采集管道（Python 3.11，rss/sitemap/api/gnews 适配器）
web/                Node 服务：REST + MCP + 静态控制台
serve00-init.sh     ★ Serv00 环境初始化脚本（幂等、可回滚、无秘密）
scripts/            采样/验收/来源发现等工具
docs/               设计与运维文档（ARCHITECTURE / DEPLOYMENT / API / DATABASE_DESIGN …）
```

## 部署指南（Serv00 实测路线）

> 详细手册见 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)，本节为入口。

### 第 0 步 · 环境初始化（先跑脚本）

仓库自带 [`serve00-init.sh`](serve00-init.sh) — Serv00 基础环境初始化/体检/修复一体脚本。
设计原则（详见 [`INIT_DESIGN.md`](INIT_DESIGN.md)）：**幂等**（跑十次与一次结果一致）、**保守**（只补缺失，绝不删除/覆盖未知内容，绝不改 devil www / SSL / DNS 平台配置）、**可回滚**（install 的每一项登记在 `.init-manifest`，uninstall 只删清单内条目）、**无秘密**（脚本内不含任何密码/Token）。

```bash
# SSH 登录你的 Serv00 账号后：
git clone https://github.com/mi1314cat/catmi-Global.git && cd catmi-Global

bash serve00-init.sh check               # 环境体检（只读）
bash serve00-init.sh install             # venv + 数据目录 + python 依赖 + 服务配置
bash serve00-init.sh install --with-cron # 需要自动采集时（默认不加，尊重平台规则）
bash serve00-init.sh status              # 查看安装清单
bash serve00-init.sh doctor              # 深度诊断
bash serve00-init.sh repair              # 按清单修复
bash serve00-init.sh uninstall           # 只删清单内条目
# 通用旗标: --dry-run 预演 / --yes 免交互
```

子命令：`check | install | repair | status | doctor | uninstall`。

### 第 1 步 · 配置秘密

```bash
mkdir -p ~/news-project
cp env.local.example ~/news-project/env.local
chmod 600 ~/news-project/env.local
vi ~/news-project/env.local        # MCP_TOKEN=自生成 60+ 位随机串；AI/LLM key 全部可选
```

### 第 2 步 · 启动采集管道（Python 3.11）

```bash
cd ~/news-project
./venv/bin/python newscli.py seed-sources --file sources.seed.json
./venv/bin/python newscli.py run          # 常驻或按 docs/DEPLOYMENT.md 配 cron
```

### 第 3 步 · 挂载 Web/MCP（Node ≥22）

- Serv00/Passenger：`devil www add <域名> public_nodejs`，以 `web/` 为应用根部署；改代码后 `pkill -f node` 生效
- 本地/裸机：`NODE_ENV=production node web/app.js`
- SQLite ≥3.45（需 FTS5）

### 第 4 步 · 首次登录

首次启动 web 服务时系统**自动创建引导管理员**（用户名 `admin`，随机强密码写入
`~/news-project/admin-credentials.txt`，权限 600，只打印一次——首登后请立即在后台改为你自己的密码）。
也可以用下面一行手工建号：

```bash
cd web && node -e "console.log(require('./lib/auth.js').createUser('admin','你的强密码','admin'))"
```

- Web 界面 `https://<域名>/` 默认开**登录门**（未登录跳登录页）；登录后 `设置` 标签可调：
  - 功能开关：公开 REST / 未登录 /api/search / 登录门
  - **端点精细控制**：每端点开关 + 限流（上限 60/分）
  - **全局限流**：公开 API ≤300/分，MCP ≤120/分（超限服务端自动截到最大）
- **MCP Token**：后台「MCP 服务」→ 创建时**勾选工具白名单**（`*` = 全部），已有 token 行内修改

### 第 5 步 · Agent/客户端接入（MCP）

```json
{"mcpServers":{"global-intelligence":{"url":"https://<你的域名>/mcp","headers":{"Authorization":"Bearer <Token>"}}}}
```

> 注意：修改 MCP 工具描述后客户端需重连才会看到新版 tools/list。

## 文档索引

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 架构与数据流
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — 部署运维手册（服务器实测基线）
- [`docs/API.md`](docs/API.md) — REST API 参考
- [`docs/DATABASE_DESIGN.md`](docs/DATABASE_DESIGN.md) — 表结构与 FTS
- [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md) — 全量测试记录（真实 HTTP 验收）
- [`OPTIMIZATION_REPORT.md`](OPTIMIZATION_REPORT.md) — 最近优化轮（R11/R12 精细化控制）报告

## License

MIT
