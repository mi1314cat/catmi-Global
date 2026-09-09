# SERVE00_AUDIT — catmi@s12.serv00.com 审计报告

> 审计时间：2026-09-09（服务器时区 CEST）
> 审计方式：全程只读（仅新增备份文件，见 CHANGELOG）
> 原始输出：`audit/A_system.txt` ~ `audit/K_*.txt`；密钥/密码一律未记录。

## 1. 系统信息
- OS: FreeBSD 14.3-RELEASE-p18 (amd64)，主机 s12.serv00.com
- CPU: Intel Xeon Silver 4214R @2.40GHz，24 核（共享）
- 物理内存（整机）: ~190 GB（用户限额 512MB，见下）
- 账号: uid=9162(catmi)，组 1000,666；Binexec: Enabled；2FA: Disabled
- 限额（devil info limits）:
  - Disk: 111.2M / 3.0G（3.62%）
  - Processes: 5 / 20
  - RAM: 122.5M / 512.0M
  - CPU: 0.2 / 100
  - ulimit: max user processes 20，open files 1500
- 账号有效期: 2036-09-06（FREE 套餐）

## 2. 平台能力（以 devil CLI 实测为准）
- devil 模块: 2fa, BinExec, DNS, FTP, Info, Lang, Mail, Mongo, MySQL, PgSQL, Port, Repo, SSL, Vhost, WWW
- WWW: 1 个站点 —— `<你的域名>`，类型 **nodejs**，目录 `/usr/home/catmi/domains/<你的域名>`
- 数据库: MySQL 0、PostgreSQL 0、MongoDB 0（全部为空）
- 端口预留: 22089/tcp、33202/udp、62006/udp（见 §6 历史遗留）
- 邮箱: catmi.serv00.net × 1（mail12.serv00.com）
- DNS zone: 0（域名 DNS 托管在外部 <free-ddns-provider> + Cloudflare）
- Cron: `crontab -l` 为空，无任何任务
- Git 仓库（平台 Repo）: 0
- 面板/服务地址: panel12.serv00.com、pma.serv00.com 等（见 devil info account）
- 平台自动备份: `~/backups/local/` 每日 ZFS 快照符号链接（root 属主，勿动）

## 3. 软件版本（实测）
- Python 3.11.13（pip 23.3.2 经 `python3 -m pip` 可用；无独立 pip3 命令）
- venv: ✅ 可创建（实测成功）
- PHP 8.3.26（CLI，各版本 0/3 worker 可用）
- Node.js v22.22.2 + npm 11.14.1
- Git 2.50.1（clone/pull 可用性待第二阶段验证，网络可达 GitHub）
- MySQL 客户端 8.0.43 / psql 16.10 / sqlite3 3.50.2 / Ruby 3.4.5 / OpenJDK 11.0.27

## 4. 网站与域名: <你的域名>
- DNS（外部 <free-ddns-provider> + Cloudflare）:
  - A/AAAA → 104.21.68.138, 172.67.195.237, 2606:4700:...（Cloudflare anycast，**已开启 CDN 代理**）
  - 源站 IP: 85.194.246.69（web12.serv00.com）；另 213.189.53.91(s12)、85.194.246.115(cache12)
- HTTPS: ✅ HTTP/2 200（经 Cloudflare，cf-ray WAW）；边缘证书: Google Trust Services WE1 签发，CN=<你的域名>，2026-07-19 → 2026-10-17（Cloudflare 自动续期，无需干预）
- 服务器侧证书: **Cloudflare Origin Certificate**，SNI 绑定 <你的域名> @85.194.246.69，2026-04-17 → **2041-04-13**（Let's Encrypt: Disabled）→ 状态正常，勿动
- HTTP(80): 200，未强制跳转 HTTPS（Cloudflare 侧可配，暂不处理）
- 本地（经用户侧出口）访问: ✅ 200，页面可达
- 网站类型: nodejs（Passenger 托管），入口 `public_nodejs/app.js`，监听 PORT 3000
- 进程: `node22 v22.22.2 (production)`，idle，内存 ~86MB VSZ
- 日志: `logs/error.log`（仅 "server is running" 启动行，健康）；access 日志由平台管理（每日文件）

## 5. 旧项目识别
### 5.1 nav-item 导航站（用户旧项目，已确认）
- 路径: `~/domains/<你的域名>/public_nodejs/`
- 来源: GitHub 开源项目 `eooce/nav-item`，通过其官方 install.sh 安装（见 .bash_history）
- 组成: Express 后端（auth/card/menu/friend/ad/upload/user 路由）+ SQLite（`database/nav.db`，82KB）+ Vite 构建前端（含 Admin 页面）+ uploads 静态目录（**尚不存在，无上传文件**）
- node_modules: 39MB
- 数据量: menus 7、sub_menus 7、cards 65、users 1（admin）、ads 0、friends 6
- 敏感项: `config.js` 含 admin 用户名/密码与 jwtSecret（已存在，值未记录）；若删除应用即随之消失
- 运行状态: 正在运行（production）
- 是否 Serve00 默认内容: 否
- 是否可删除: **可以（用户已确认为旧项目），但需先备份（已完成）并确认站点去留方案**

### 5.2 sing-box 时代遗留（无文件残留）
- 证据: `.bash_history` 含 `bash <(curl -Ls .../eooce/Sing-box/.../reset.sh)`；devil 端口预留 3 个
- 现状: 家目录全盘搜索 **无** sing-box/xray/v2ray/argo/cloudflared 残留文件；无相关进程；crontab 为空
- 遗留: 3 个端口预留（22089/tcp、33202/udp、62006/udp）——用途已消失，可清理（待确认）

### 5.3 Serve00 原始/平台内容（保留）
- `~/backups/`（root:1004，ZFS 每日快照入口）
- `logs/`（平台访问日志符号链接）
- `.bash_profile`、`.wget-hsts`、`.bash_history`
- devil/Vhost/SSL/WWW 平台配置

## 6. 磁盘与 inode
- 磁盘: 111.2M / 3.0G；大头: node_modules 39M、.npm 44M、.cache 28M、.npm-global 512B
- 文件总数（home）: 8,844
- inode 平台层面充足（ZFS，无独立 inode 限额压力）

## 7. 网络连通性（服务器实测）
- DNS/HTTPS: OK（python urllib → example.com 200）
- GitHub: 200 ✅；PyPI: 200 ✅
- RSS 试测: `feeds.bbci.co.uk/news/world.xml` HEAD → 404（该端点已失效/变动，网络本身通；第二阶段再选有效源）
- pip / venv: OK

## 8. 审计结论
1. 除 nav-item 导航站和 3 个端口预留外，服务器上**没有其他旧项目或未知文件**，环境干净。
2. SSL/域名/CDN 链路配置完整且长期有效，第一阶段不需要申请或更换任何证书。
3. 主要清理空间: `.cache` + `.npm`（72M，可再生缓存）。
4. 唯一 Unknown: 无（全部条目已识别）。
