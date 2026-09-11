# INIT_DESIGN — serve00-init.sh 设计说明

> 版本 1.0.0（2026-09-09）

## 1. 需求回顾

把第一次人工初始化固化为可重复脚本，满足：幂等、保守、dry-run、保护域名/SSL、不碰已有 cron、不存秘密、可回滚。

## 2. 核心设计决策

### 2.1 Manifest 清单 = 幂等 + 可回滚的基石
- install 创建的每一项都登记到 `~/news-project/.init-manifest`（`type|path` 行，重复登记被 `grep -qxF` 去重）。
- 已存在的东西**跳过且不覆盖**（env.example、PROJECT_README.txt、venv、cron 标记块全部如此）。
- uninstall **只**按 manifest 倒序删除；目录用 `rmdir`（非空自动跳过），所以未登记的用户文件永远不会被删。
- 防御性保护：uninstall 循环里硬编码拒绝 `$HOME/domains*` 与 `$HOME/backups*`（平台快照）。

### 2.2 Cron 默认只读
用户红线"不能覆盖已有 Cron"。实现：
- check/status/doctor 只 `crontab -l` 统计并报告是否存在标记块。
- `--with-cron` 才写入，且写入的是**全注释占位块**（零功能风险），先备份到 `~/news-backups/init/crontab-backup-*.txt`。
- 标记块 `# BEGIN/END serve00-news` 让追加/移除都可精确定位、可重复（幂等：已存在则跳过）。

### 2.3 域名/SSL 只读
- `check_web`/`check_ssl` 只调用 `devil www list` / `devil ssl www list`（列出型子命令），**从不**调用任何写型子命令。
- 证书到期日从 devil 输出中用正则 `[0-9]{4}\.[0-9]{2}\.[0-9]{2}` 提取（取最后一个匹配=过期日），不依赖列对齐——避免 CommonName 词数变化导致错位。
- 私钥相关命令（如 `devil ssl www get`，会交互索要密码且无 tty 时回显）被**明确禁用**，脚本注释中写明原因。

### 2.4 Dry-run 机制
- 统一动作执行器 `act()`：`DRY_RUN=1` 时打印 `[dry-run] <cmd>` 而不执行；install/repair/uninstall 的所有变更路径都经 `act()`。
- 检查函数本身只读，dry-run 下照常运行，保证演练输出仍有信息量。

### 2.5 备份区放在项目外
`~/news-backups/init/` 独立于 `~/news-project/`——uninstall 项目不会连带删掉 crontab 备份；`--purge-backups` 才清除。这也与平台 `~/backups/`（ZFS 快照，root 属主）完全隔离。

### 2.6 阈值（doctor）
| 指标 | 来源 | 阈值 |
|---|---|---|
| 磁盘使用率 | `df -h ~` | ≥80% WARN |
| 内存/进程/配额 | `devil info limits`（ANSI 剥离后 grep） | RAM ≥80% WARN；进程上限 20 提示 |
| 证书剩余天数 | devil ssl www list + `date -j -f`（BSD）/`date -d`（GNU）双路径 | <30 天 WARN，<0 ERR |
| HTTPS | `curl -sI` 状态码 | 非 2xx/3xx ERR |
| 运行时 | python3/git/sqlite3 | 缺失 ERR |

### 2.7 FreeBSD 可移植性
- `#!/usr/bin/env bash`；无 GNU 专属工具：`tac` 用 awk 反转替代；`grep -cvE` 替代 BRE `\|`；日期解析 BSD/GNU 双路径。
- `devil` 输出含 ANSI 色码，统一 `sed -e 's/\x1b\[[0-9;]*m//g'` 剥离后再解析。
- 主动声明的环境限制（写在 doctor 结论里）：FreeBSD 无官方 Playwright/Chromium —— JS 站点策略由第二阶段研究文档决定，脚本不擅自安装。

### 2.8 秘密纪律
脚本内零秘密；`env.example` 全空值；文档/日志只允许"已配置/已验证"措辞。AI key 未来运行时经 `env.local`（不入 Git）注入。

## 3. 模式与验收对照

| 验收项 | 实现点 |
|---|---|
| check/install/status/doctor 正常 | 各自独立函数，见脚本入口 case |
| dry-run 正常 | `act()` 全覆盖变更路径 |
| 重复运行不破坏 | ensure/manifest 去重 + 已存在跳过（服务器实测两次 install 对比） |
| 不覆盖现有 Cron | 默认零写入；--with-cron 注释占位 + 备份 |
| 不删除未知文件 | uninstall 只认 manifest + rmdir 语义 + 受保护路径拒绝 |
| 不破坏 Serve00/域名/SSL | 全脚本无 devil 写调用（grep 可审计） |
| 不泄露秘密 | 无硬编码值；证书只输出日期与 CN 名称 |
