# SERVE00_RECOVERY_PLAN — 恢复/清理计划

> **状态：已执行完毕（2026-09-09，用户确认后）**。执行记录见 SERVE00_CHANGELOG.md。
> 执行结果：家目录 111M → 551K；端口预留 0；缓存 0；history 清空；https://<你的域名> 保持 200。
> 以下为当时的计划内容，供追溯。

> 原则：先备份（已完成），再清理；UNKNOWN 不动；宁可保留，不可误删。
> 备份位置：服务器 `~/backup/nav-item-app-2026-09-09.tar.gz`（含代码+nav.db，不含 node_modules）；
> 本地 `serve00-catmi/backup/` 同名副本；平台另有 ZFS 每日快照兜底。

## 一、拟清理项（均待确认）

| # | 对象 | 内容 | 大小 | 风险 | 建议 |
|---|---|---|---|---|---|
| 1 | 旧导航站 | `public_nodejs/` 内的代码、路由、public 前端、nav.db、config.js | ~1M(+39M node_modules) | 已备份，可回滚 | 见下方方案选择 |
| 2 | node_modules | `public_nodejs/node_modules/` | 39M | 无（可再生） | 随方案 1b 一起删 |
| 3 | 缓存 | `~/.cache`(28M) + `~/.npm`(44M) | 72M | 无（可再生） | 建议清理，释放 72M |
| 4 | 端口预留 | 22089/tcp、33202/udp、62006/udp（sing-box 遗留） | — | 无进程占用 | 建议清理（或保留 1 个 TCP 供第二阶段备用） |
| 5 | .bash_history | 含 sing-box/nav-item 安装命令记录 | 286B | 仅隐私层面 | 可选：清空或保留 |

## 二、拟保留项（不动）

- 域名绑定（devil www，nodejs 类型或改后重建）、DNS（外部 <free-ddns-provider> + Cloudflare）
- SSL：Cloudflare Origin 证书（至 2041-04-13）+ Cloudflare 边缘自动证书
- `~/backups/`（平台 ZFS 快照）、`logs/`（平台日志）
- 邮箱 catmi.serv00.net ×1、Binexec（Enabled，第二阶段跑 Python/自定义程序需要）
- `.bash_profile`、`.npm-global`

## 三、导航站处理方案（三选一）

### 方案 A：推荐 —— 换成零依赖极简页面（保持 nodejs 类型）
1. 用新 `app.js`（纯 Node 内置 http，无任何依赖）替换旧入口：只返回一个极简静态 index.html
2. 删除 routes/、database/、public/(旧资源)、config.js、db.js、package*.json、node_modules/、tmp/
3. 触碰 `tmp/restart.txt` 让 Passenger 重启（或等待自动重启）
4. 优点：不触碰 devil www/SSL/域名配置，HTTPS 链路零风险；磁盘回收 ~40M；进程内存占用更低
5. 结果：`https://<你的域名>` 返回一个简单测试页（后续第二阶段可再替换）

### 方案 B：改成 PHP 静态站
- `devil www del <你的域名>` → `devil www add <你的域名> php` → public_html 放默认页
- ⚠️ 风险：删除站点可能连带 SSL 绑定；`devil ssl www get` 因交互式密码回显风险不可用于导出。除非能从 Cloudflare 控制台重新签发 Origin 证书，否则**不建议**

### 方案 C：全部保留现状
- 什么都不删，仅清理缓存（.cache/.npm）与端口（可选）

## 四、执行后验证清单（无论哪个方案）

1. `devil www list` 正常
2. `curl -I https://<你的域名>` → 200（服务器侧 + 本地侧）
3. 磁盘占用复查（devil info limits）
4. python3 -m venv、git --version、crontab -l 复查
5. CHANGELOG 登记全部动作

## 五、待用户确认

1. 导航站处理选 A / B / C？
2. 缓存 72M 是否清理？
3. 端口预留 3 个：全删 / 保留 22089/tcp 一个 / 全保留？
4. .bash_history 清空与否？
