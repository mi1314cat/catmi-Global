# INIT_CHANGELOG — serve00-init.sh 版本与变更记录

## v1.0.1 — 2026-09-09（服务器实测发现缺陷后修复）
- **修复 ensure_dir 只处理单个参数的缺陷**：v1.0.0 中 `ensure_dir a b c` 只创建/登记 `a`，导致 news-data 子目录、sites/、备份目录未创建（服务器 install 实测暴露）。修复后多参数循环处理，逐项登记 manifest。
- 复跑 install（幂等）自动补齐缺失目录，无需回滚。

## v1.0.0 — 2026-09-09
- 首版。
- 模式：check / status / install / repair / doctor / uninstall / help；选项：--dry-run / --with-cron / --remove-cron / --yes / --purge-backups。
- Manifest（`.init-manifest`）驱动的幂等 install 与受控 uninstall；受保护路径硬拒绝（domains/backups）。
- Cron 策略：默认只读；--with-cron 写入全注释占位块（先备份）；--remove-cron 按标记块移除（先备份）。
- SSL 检查：devil ssl www list 只读解析到期日（正则提取，BSD/GNU date 双路径），绝不输出私钥；明确禁用 `devil ssl www get`（交互回显密码风险）。
- FreeBSD 适配：无 GNU tac（awk 反转）、grep -E、devil ANSI 剥离、dry-run 执行器 act()。
- 服务器实测：check/status/doctor/install --dry-run/install/install(幂等复跑)/uninstall --dry-run 全部通过；受保护域名 HTTPS 全程 200；crontab 未被触碰。

## 计划中的后续版本
- v1.1：采集系统 cron 激活辅助（phase 3 需要）、`--json` 输出（供面板/监控用）、venv 依赖锁定（requirements 冻结 + 校验和）。
