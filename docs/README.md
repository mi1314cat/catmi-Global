# README — serve00-init.sh（Serv00 新闻系统初始化脚本）

> 版本 1.0.0 · 目标主机: s12.serv00.com（FreeBSD 14.3）· 受保护域名: <你的域名>
> 设计细节见 `INIT_DESIGN.md`；脚本版本历史见 `INIT_CHANGELOG.md`。

## 一、这个脚本做什么

把新闻系统需要的**基础环境**固化成幂等脚本：检查 → 补缺失 → 验证。
它**不是**重置脚本：绝不删除未知文件，绝不覆盖已有配置，绝不触碰域名/SSL/DNS/平台设置。

创建的内容（install 时，全部登记在 `~/news-project/.init-manifest`）：

```
~/news-project/
├── serve00-init.sh README.md INIT_DESIGN.md INIT_CHANGELOG.md
├── news-data/{articles,images,database,cache,logs}
├── sites/                 # 未来网站适配器
├── venv/                  # Python 3.11 虚拟环境
├── env.example            # 环境变量模板（空值，无秘密）
└── PROJECT_README.txt
~/news-backups/init/       # 脚本自身的备份区（crontab 备份、损坏 venv 等）
```

## 二、使用方法

```bash
cd ~/news-project

./serve00-init.sh check            # 只检查，不改任何东西
./serve00-init.sh status           # 简要状态
./serve00-init.sh doctor           # 全面诊断 + 阈值结论
./serve00-init.sh install          # 创建缺失结构（幂等，可反复执行）
./serve00-init.sh install --dry-run   # 演练：只显示将执行的动作
./serve00-init.sh repair           # 修复目录/损坏 venv（域名/SSL/cron 绝不触碰）
./serve00-init.sh uninstall        # 只删除 manifest 登记的条目（交互确认）
./serve00-init.sh uninstall --yes --remove-cron   # 非交互 + 移除 cron 标记块
./serve00-init.sh uninstall --purge-backups       # 同时删除备份区（默认保留）
```

### Cron 策略（重要）

- **默认绝不修改 crontab。**
- `install --with-cron` 会先备份 crontab 再追加一个**全部注释的占位块**（`# BEGIN/END serve00-news`），不激活任何任务；重复执行自动跳过（幂等）。
- 实际调度任务在后续阶段用同一个标记块激活。
- `uninstall --remove-cron` 只移除该标记块，其余 cron 行原样保留（移除前再备份一次）。

## 三、回滚 / 卸载

| 想恢复的东西 | 方法 |
|---|---|
| install 建的目录/venv/模板 | `./serve00-init.sh uninstall`（按 manifest 倒序删除；非空目录跳过并提示） |
| crontab 被标记块改动 | uninstall 前有备份 `~/news-backups/init/crontab-backup-*.txt`；或 `crontab 备份文件` 手动恢复 |
| 损坏的 venv | `./serve00-init.sh repair`（旧 venv 先移入备份再重建） |
| 旧导航站（如需） | `tar -xzf ~/backup/nav-item-app-2026-09-09.tar.gz -C ~/domains/<你的域名>/` + touch restart.txt |
| 整机兜底 | 平台 ZFS 每日快照 `~/backups/local/日期/` |

## 四、保护承诺（任何模式都成立）

1. 不执行 `devil www del/add`、`devil ssl` 写操作、DNS 修改。
2. 不输出、不保存任何私钥/密码/Token（env.example 全是空值模板）。
3. 不删除未知文件：uninstall 只认 manifest；manifest 中若出现 `~/domains`、`~/backups` 路径会**拒绝执行**。
4. 平台 ZFS 快照目录 `~/backups/` 永不触碰。
5. `--dry-run` 下零副作用（只打印动作）。

## 五、doctor 会报告什么

系统/运行时/Web/SSL/网络/Cron/项目 七组检查 + 阈值判断：
磁盘 ≥80%、内存 ≥80%、证书剩余 <30 天、HTTPS 非 200、Python/Git/SQLite 缺失 —— 各自给出 WARN/ERR 与明确原因；环境做不到的事（如 FreeBSD 无 Playwright）明确报告而不是硬装。
