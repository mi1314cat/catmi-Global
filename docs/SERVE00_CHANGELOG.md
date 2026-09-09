# SERVE00_CHANGELOG — 变更记录

> 每一次对服务器的修改都必须登记：时间 / 对象 / 动作 / 备份 / 回滚。

| 日期(UTC) | 对象 | 动作 | 类型 | 备份/回滚 |
|---|---|---|---|---|
| 2026-09-09 | /usr/home/catmi/backup/ | 新建备份目录；写入 devil-state-2026-09-09.txt；打包 nav-item-app-2026-09-09.tar.gz（不含 node_modules，含 nav.db/config.js，权限仅属主） | 只增 | 本备份即回滚点；另有平台 ZFS 每日快照 |
| 2026-09-09 | ~/backup/ssl/ | 尝试 devil ssl www get 导出证书被放弃（命令交互索要密码且会回显，有泄露风险）；已删除其产生的错误文本文件（仅 3 行报错文本，无秘密） | 自清理 | 无影响；SSL 本身未动 |
| 2026-09-09 | 本地工作区 | 审计输出 audit/A~K 与备份副本 nav-item-app tarball、devil-state 存于本地 | 只增 | — |

| 2026-09-09 | public_nodejs/ | **执行清理（用户确认）**：部署零依赖极简 app.js + index.html；删除旧 nav-item 全部组件（routes/ database/ config.js db.js package*.json node_modules/ public/assets 等） | ✅ 备份 `~/backup/nav-item-app-2026-09-09.tar.gz`（服务器+本地双份）+ ZFS 快照 | 解包 tarball 还原全部文件 |
| 2026-09-09 | node 进程 | touch restart.txt 未触发重载 → kill 旧进程 78955，Passenger 重生 PID 82844 运行新应用 | — | 新应用已验证；旧应用可从备份恢复 |
| 2026-09-09 | devil port | 删除全部 3 个预留端口（22089/tcp、33202/udp、62006/udp，sing-box 遗留） | — | `devil port add tcp/udp <端口>` 可重新申请 |
| 2026-09-09 | ~/.cache ~/.npm | 清除可再生缓存（node-gyp/npm cache，72M） | — | 无需恢复（自动再生） |
| 2026-09-09 | ~/.bash_history | 清空（0 字节） | — | 无需恢复 |
| 2026-09-09 | 本地工作区 | 清除 /tmp 密码临时文件 | — | — |

| 2026-09-09 | ~/news-project/ | **阶段1**：serve00-init.sh v1.0.0→v1.0.1 部署并实测（check/status/install×3/repair/doctor/uninstall-dry-run/--dry-run）；创建项目目录树/venv(pip 26.2.1)/env.example/PROJECT_README；manifest 12 条 | manifest 即回滚点 | uninstall --yes 可完整移除 |
| 2026-09-09 | ~/news-lab/ | **阶段2**：创建实验室 + venv(--system-site-packages)；pip 源码编译安装 lxml 6.1.3 / orjson 3.12.0(CARGO_BUILD_JOBS=2) / msgspec / scrapling 0.4.15 / trafilatura 2.2.0 / markdownify；安装失败证据（curl_cffi/playwright/crawl4ai）完整记录于 results/install_report.txt | venv 可删重建； wheels 缓存已清 | `pip freeze` 可复现 |
| 2026-09-09 | ~/news-lab/results/ | 运行 8 个测试脚本（scrapling/crawl4ai/article_extract/image_extract/benchmark/pipeline_prototype/gnn_cluster/adaptive_retest）；prototype.db 建表+5文章+5图片+5故事 | 结果已同步本地 workspace | — |
| 2026-09-09 | ~/.cache/pip ~/.cargo/registry | 清理构建缓存（64M + 547M，可再生） | — | 首次编译会重新下载 |
| 2026-09-09 | 服务器 news-project/ | 同步 7 份研究/决策文档 | 本地为主副本 | — |

> 审计期间执行的其余全部操作均为只读命令（uname/df/ps/devil list/sqlite3 只读查询/curl HEAD 等）。
> 唯一例外：venv 创建测试在服务器 /tmp 中进行并已删除（batchF）。
