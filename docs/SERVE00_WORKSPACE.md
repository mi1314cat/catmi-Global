# SERVE00_WORKSPACE — catmi@s12.serv00.com

> 长期项目主文档。**禁止记录任何密码 / Token / API Key / SSL 私钥。**
> 详细审计见 `SERVE00_AUDIT.md`；所有变更见 `SERVE00_CHANGELOG.md`。

## 1. 服务器环境
- s12.serv00.com，FreeBSD 14.3-RELEASE-p18 amd64，FREE 套餐，账号有效期 2036-09-06
- SSH 密码登录已验证可用（密码不写入任何文档）
- 限额: 磁盘 3.0G（用 111M）、进程 20（用 5）、内存 512M（用 122M）

## 2. 项目结构（服务器侧）
```
/usr/home/catmi/
├── backup/                     # 本次接管创建的备份（见 CHANGELOG）
│   ├── nav-item-app-2026-09-09.tar.gz
│   └── devil-state-2026-09-09.txt
├── backups/                    # [平台] ZFS 每日快照，勿动
├── domains/
│   └── <你的域名>/
│       ├── logs/               # [平台] 访问日志
│       └── public_nodejs/      # 旧项目: eooce/nav-item 导航站（待处理）
│           ├── app.js db.js config.js package.json
│           ├── routes/ database/nav.db public/ tmp/
│           └── node_modules/ (39M)
├── .cache/ (28M)  .npm/ (44M)  # 可再生缓存（清理候选）
└── .npm-global/ .bash_profile .bash_history .wget-hsts
```

## 3. 网站 / 域名 / SSL
- 域名: <你的域名>（外部 <free-ddns-provider> DNS + Cloudflare CDN 代理）
- 站点类型: nodejs（Passenger），入口 public_nodejs/app.js
- HTTPS: 正常（Cloudflare 边缘证书自动续期）；源站证书: Cloudflare Origin，有效期至 2041-04-13
- 状态: **已验证** —— https 200（服务器侧与本地侧均确认）
- 保护要求: DNS / 域名绑定 / SSL / Web 基础配置一律不动

## 4. 数据库
- 平台 MySQL/PostgreSQL/MongoDB: 均未使用（0 个）
- 应用内 SQLite: public_nodejs/database/nav.db（65 卡片/7 菜单/1 管理员，已备份）

## 5. Cron
- crontab 为空 —— 未发现任何计划任务

## 6. Python / Git
- Python 3.11.13，pip(via -m) 23.3.2，venv 实测可用
- Git 2.50.1；服务器上无 git 仓库；GitHub 可达

## 7. 当前状态（2026-09-09 第二次更新：阶段1+2 完成）
- **阶段1（初始化脚本）✅**：`~/news-project/serve00-init.sh` v1.0.1，check/status/install/repair/doctor/uninstall/--dry-run 全部服务器实测通过，幂等复跑验证，crontab/域名/SSL 零触碰
- **阶段2（抓取研究+实测）✅**：`~/news-lab/` 实验室建成
  - ✅ Scrapling 0.4.15 解析层（lxml 6.1.3 / orjson 3.12.0 均源码编译成功，Rust 工具链可用）
  - ❌ Scrapling Fetcher（curl_cffi 上游拒绝 FreeBSD）/ playwright（versions:none）/ Crawl4AI（级联失败）——证据完整
  - ✅ trafilatura 2.2.0 正文提取 / feedparser RSS / httpx 抓取
  - ✅ 端到端原型：BBC RSS 5篇→正文→主图→去重→指纹聚类→SQLite，11.4s / 峰值 87MB
  - ✅ 跨源聚类：Google News 92 条 → 19 簇（4 个多来源簇），0.001s
  - 家目录 53M / 磁盘配额 ~1.7%（pip/cargo 构建缓存已清理）
- 服务器现状：占位站点照常 https 200；`~/news-project/`（脚本+文档+venv+数据目录）；`~/news-lab/`（实验室+测试结果）；旧 nav-item 备份仍在 `~/backup/` 与本地

## 8. 交付文档（本地 `serve00-catmi/` = 服务器 `~/news-project/`）
- 阶段1: README.md / INIT_DESIGN.md / INIT_CHANGELOG.md + serve00-init.sh
- 阶段2: SCRAPER_RESEARCH / SCRAPER_BENCHMARK / SCRAPER_ARCHITECTURE / SCRAPER_DECISIONS
- GitHub 研究: GITHUB_PROJECT_RESEARCH / GITHUB_LICENSES / TECH_STACK_DECISION
- 实验室: news-lab/（8 个测试脚本 + results/ 原始输出 + prototype.db）

## 9. 下一步（等待用户确认后）
- 阶段3 实现：newscli.py 管道 + sites/ 适配器 + AI 管线（需用户提供 OpenAI-compatible key，走 env.local）+ cron 激活 + Web 阅读
- 待用户决策：cron 间隔（10-15min）、AI 供应商与模型、是否启用 votes 反馈环、JS 站点是否需要外部渲染服务
