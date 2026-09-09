# DEPLOYMENT — 部署与运维手册

> 实测基线: s12.serv00.com · FreeBSD 14.3 · Python 3.11.13 · Node v22.22.2 · 2026-09-09

## 1. 目录布局（服务器）

```
~/news-project/                    # 管道 + 配置 + 数据
├── venv/                          # Python venv（trafilatura/scrapling 栈, ~450M）
├── news/                          # 采集管道包（12 模块）
├── sources.seed.json              # 49 源注册表（全部实测验证）
├── env.local          (600)       # MCP_TOKEN / 可选 AI keys（绝不入文档）
├── news-data/
│   ├── database/news.db*          # SQLite WAL（唯一持久数据源）
│   ├── images/YYYY-MM/            # 72h 图片
│   ├── cache/date/                # 24h 原始页 gz
│   └── logs/{cron,web}.log        # 日志（web.log 5MB 轮转）
├── news-backups/                  # news-*.db.gz × 7
└── *.md                           # 15 份文档（与本地 workspace 同步）

~/domains/<你的域名>/
└── public_nodejs/                 # Passenger Node 服务层
    ├── app.js                     # REST API + MCP + 静态托管（零框架）
    ├── lib/newsdb.js              # 只读查询层（node:sqlite）
    ├── public/                    # Web UI（Phase 7）
    └── node_modules/              # @modelcontextprotocol/sdk 1.30 (29M)
```

## 2. 进程模型（双进程, 已验证）
- **Python cron one-shot**（每 10min, lockf 防重）: scan→fetch→images→cluster→trending→cleanup
- **Node Passenger**（按需常驻）: /api/* + /mcp + 静态页
- 共享同一 WAL SQLite；Passenger 崩溃自动重生（实测）；管道崩溃靠 cron 重入 + 任务队列断点

## 3. 首次部署（或重建）
```sh
# 1) 基础设施（幂等, 已有 v1.0.1 脚本）
sh serve00-init.sh status   # 检查站点/SSL/配额
# 2) 管道代码
rsync news/ ~/news-project/news/  # 或 scp -r
# 3) venv（首次: 15 分钟源码构建; 重建: 复制 lab venv site-packages）
# 4) 初始化
cd ~/news-project && ./venv/bin/python -m news.newsctl init-db
./venv/bin/python -m news.newsctl seed-sources --file sources.seed.json
# 5) 服务层（备份旧 app.js → 部署新 → kill 旧进程 → Passenger 按需重生）
cp ~/domains/.../public_nodejs/app.js ~/backup/app.js.v0.bak   # 已做
scp web/app.js → public_nodejs/app.js; scp web/lib/*.js → public_nodejs/lib/
cd public_nodejs && npm install @modelcontextprotocol/sdk@1.30.0
kill 旧 node 进程; curl https://<你的域名>/api/health   # 验证
# 6) 秘密
echo "MCP_TOKEN=$(openssl rand -hex 32)" >> ~/news-project/env.local; chmod 600 env.local
# 7) cron（见 §4）
```

## 4. cron 表（已装, crontab -l 核验）
```
*/10 * * * * lockf -t 0 /tmp/news-run.lock … newsctl run   # 全管道（水位门控）
35  * * * * … newsctl cleanup                               # 滚动清理
10  4 * * * … newsctl backup                                # 每日备份（保 7 份）
20  4 * * * … newsctl doctor                                # 每日体检
```
调频: 改 crontab 即可；run 内部按 sources.poll_seconds 决定实际抓取（P0 10min/P1 30-60min/P2 2-6h）

## 5. 运维命令（全部已实测）
| 操作 | 命令 |
|---|---|
| 状态 | `newsctl status`（文章/事件/图片/任务/水位/last_run） |
| 体检 | `newsctl doctor`（quick_check/FTS 漂移/停用源/卡死任务/WAL） |
| 手动全管道 | `newsctl run`（或 scan/fetch/images/cluster/trending/cleanup 分步） |
| 备份/恢复 | `newsctl backup` / 手动: gunzip → 替换 news.db → 无需重启（读连接自动重开） |
| 源增删 | 改 sources.seed.json → `seed-sources`；坏源 5 连败自动停用（重置 consecutive_failures 复活） |
| 服务重启 | `kill $(pgrep -f "node22.*myp")` → 下一个请求自动重生 |
| Web 日志 | news-data/logs/web.log（JSON 行, 已脱敏） |

## 6. 恢复时间目标
- 管道级故障（进程死）: ≤10min（下个 cron 槽）
- 服务级故障（Passenger 死）: <2s（按需重生, 实测）
- 数据级故障（DB 损坏）: <5min（restore 最新备份 + 队列续跑）
- 全盘重建: <30min（venv 复制法）— v1.0.1 init 脚本 + 本手册 §3
