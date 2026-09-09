# SERVE00_WATCHDOG — Serve00 Cron 自动运行 + GitHub Actions 外部 Watchdog

> 日期: 2026-09-09 · 状态: 生产运行中
> 核心原则: **Serve00 Cron 是主调度器**（系统即使一天不跑 Watchdog 也正常采集）；GitHub Actions 只是每天一次的外部检查 + 最小修复。

## 1. 总体架构

```
                GitHub Actions（每天 04:25 北京时间）
                    │  SSH（密钥认证 + Host Key 固定）
                    ▼
                 Serve00 (s12.serv00.com, FreeBSD)
                    │
      ┌─────────────┴─────────────┐
      ▼                           ▼
   Cron（用户 crontab）        Passenger（平台托管）
      ▼                           ▼
  scripts/run-collector.sh      web/app.js → REST + MCP
      ▼
  news.newsctl run（lockf 防重叠）
      ▼
  SQLite (news.db) → 热点/事件/搜索/MCP
```

- Cron（one-shot，跑完即退）与 Passenger（Web/MCP）生命周期完全分离，互不干扰
- 不存在任何常驻 Watchdog / 后台循环 / 防回收机制

## 2. Serve00 官方机制确认（2026-09-09 复核）

| 机制 | 官方确认（serv00.com 文档/落地页） | 本项目用法 |
|---|---|---|
| Cron | 用户 crontab 可用（`crontab -l/-e`，标准 FreeBSD cron） | 4 条任务装在用户 crontab，带 Marker 区块 |
| @reboot/@hourly | FreeBSD cron 语法支持，但本服务不依赖（主机重启不由用户控制，@reboot 不可靠） | 不使用 @reboot；每 10 分钟 run + 每时 cleanup + 每日 backup/doctor |
| Passenger | Web/MCP 由平台 Passenger 托管（ devil www 管理），平台自动回收空闲进程 | 不做任何"保活"（遵守平台生命周期） |
| 进程限制 | 免费档系统进程受限（落地页: 15 processes / 512MB RAM 档） | 采集 one-shot（峰值 1 个 python + lockf），跑完即退 |
| 后台进程 | 禁止常驻后台服务 | 无（GitHub Actions 亦非常驻） |

## 3. Cron 管理（Marker 区块, 幂等）

Marker：
```cron
# CATMI_GLOBAL_COLLECTOR_BEGIN
*/10 * * * * /home/<user>/news-project/scripts/run-collector.sh >> $HOME/news-project/news-data/logs/cron.log 2>&1
35 * * * * ... newsctl cleanup ...
10 4 * * * ... newsctl backup ...
20 4 * * * ... newsctl doctor ...
# CATMI_GLOBAL_COLLECTOR_END
```

| 脚本 | 作用 | 关键保证 |
|---|---|---|
| `scripts/install-cron.sh` | 幂等安装/修复区块 | 只替换自己的区块；**用户其他 Cron 原样保留**；项目旧式无 Marker 条目精确迁移（仅匹配 `news.newsctl`/`run-collector.sh` 模式）；连跑 N 次只有 1 个区块 |
| `scripts/check-cron.sh` | 机器可读检查 | `CRON_STATUS=OK/MISSING/DUPLICATE/INVALID` + 原因；校验 marker 平衡/重复/runner 可执行/路径存在；**不打印任何 Secret** |
| `scripts/remove-cron.sh` | 只删区块 | 其他 Cron 原样保留 |
| `scripts/run-collector.sh` | 采集唯一入口 | `lockf -t 0` 防重叠（繁忙=exit 75 → 跳过不改状态）；写 `news-data/state/collector-state.json`；one-shot |

绝不用 `echo ... | crontab -` 全量重建——永远「读现有 → 过滤区块 → 原样保留其他 → 追加区块」。

## 4. Collector 健康状态（与 Cron 状态严格区分）

`news-data/state/collector-state.json`（ISO 8601 UTC 时间）:
```json
{"last_started_at":"2026-09-09T13:25:23Z","last_finished_at":"...Z","last_success_at":"...Z",
 "last_status":"success|failed|running","last_error":null,"last_exit_code":0,"last_duration_s":120}
```

Watchdog 判定（`watchdog-report.sh`）:
| 情况 | 判定 | 处理 |
|---|---|---|
| pgrep 到 newsctl 进程 | `RUNNING` | 什么都不做（HEALTHY） |
| 72 分钟内成功过 | `OK` | 什么都不做（HEALTHY） |
| 最近（12h 内）失败 | `FAILED_RECENT` | 只记录（DEGRADED）；**不重建/不删 Cron** |
| started 无 finished 且进程不在 | `STALE` | 标记（DEGRADED）；下一轮 cron 自愈，不 kill 不删锁 |
| 状态文件缺失 | `UNKNOWN` | 标记（DEGRADED） |

## 5. Stale lock 处理

**机制上不存在 stale lock**：锁用 FreeBSD `lockf`（advisory lock），进程死亡锁自动释放，`/tmp/news-run.lock` 只是锁目标文件（无进程时为惰性空文件）。Watchdog **永不删除锁文件**（删除会与运行中的采集竞态）；"清理"仅当出现新的锁机制时才需要重新设计。TTL 概念由状态文件的成功时间窗（72 分钟 ≈ 6-7 个 cron 周期）承担。

## 6. GitHub Actions Watchdog

- 文件: `.github/workflows/serv00-watchdog.yml`
- 触发: `schedule cron "25 20 * * *"`（**UTC 20:25 = 北京时间 04:25，每天一次**）+ `workflow_dispatch`（手动 Run workflow）
- 权限: `permissions: contents: read`（最小权限）
- 并发: `concurrency: serv00-watchdog`（不并行）
- 流程: SSH（密钥）→ 运行 `scripts/watchdog-report.sh` → 解析输出 → Step Summary
- 结果码: `HEALTHY`/`RECOVERED` → 退出 0；`DEGRADED` → 退出 1（日志/摘要可见，但不视为构建失败）；`FAIL` → 退出 2

### GitHub Secrets（只列名称）
```
SERV00_HOST            # 如 s12.serv00.com
SERV00_PORT            # 22
SERV00_USER            # catmi
SERV00_SSH_PRIVATE_KEY # Watchdog 专用 ed25519 私钥（公钥已装在服务器 authorized_keys，限制为仅可执行 watchdog-report.sh）
```
（未使用 `MCP_HEALTHCHECK_TOKEN`——MCP 健康检查已在服务器侧由 `watchdog-report.sh`/诊断完成，无需外部 token，减少 Secret 面。）

### SSH 安全
- **Host Key 固定**：`.github/known_hosts.serv00`（3 种算法公钥，公开信息）→ workflow 复制为 known_hosts + `StrictHostKeyChecking=yes`，**绝不绕过主机验证**
- 私钥只经 `printf '%s\n' "$SECRET" > file` 落盘，**永不 echo / set -x / 打印**
- 服务器侧 authorized_keys 对 watchdog 公钥加 `command=".../watchdog-report.sh",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding` 限制——即使私钥泄露也只能跑诊断脚本

## 7. 故障恢复策略（Watchdog 行为矩阵）

| 场景 | 行为 |
|---|---|
| SSH 失败 | Workflow FAIL；**不修改 Serve00**；等下次检查（绝不为此关 Host Key 校验） |
| Cron MISSING/INVALID/DUPLICATE | `install-cron.sh` 幂等修复（只动 Marker 区块）→ 复检 → `RECOVERED` |
| Collector 单次失败 | 记录；**不重建 Cron**（DEGRADED） |
| Collector STALE | 标记（DEGRADED）；依赖下轮 cron 自愈；不 kill -9 / 不删锁 / 不重启服务 |
| 项目文件损坏 | `RESULT=FAIL`；不自动修复（人工介入） |

## 8. 排查指引
1. Actions 页看最近一次 run 的 Summary（键值对一目了然）
2. SSH 上服务器：`scripts/check-cron.sh`（Cron 层）、`cat news-data/state/collector-state.json`（采集层）、`tail -50 news-data/logs/cron.log`（细节）
3. 手动触发：GitHub → Actions → serv00-watchdog → Run workflow
4. 手动重装 Cron：服务器上跑 `scripts/install-cron.sh`

## 9. 如何禁用 Watchdog
- 停用 GitHub 检查: Actions → serv00-watchdog → Disable workflow（Serve00 Cron 继续工作，采集不受影响）
- 停用项目 Cron: 服务器 `scripts/remove-cron.sh`（区块整体移除，其他 Cron 保留）
