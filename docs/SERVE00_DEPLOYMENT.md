# SERVE00_DEPLOYMENT — 部署记录

> 第一阶段仅部署了占位页面。新闻系统组件一律在第二阶段获得用户指令后才开始。

## D1. 极简占位站点（2026-09-09，第一阶段恢复产物）

- 位置: `~/domains/<你的域名>/public_nodejs/`
- 组成:
  - `app.js` —— 零依赖（仅 Node 内置 http/fs/path），静态服务 public/，监听 `process.env.PORT`（Passenger 注入 3000）
  - `public/index.html` —— 占位页「服务运行中 / 环境已清理」
  - `tmp/restart.txt` —— Passenger 重启信号文件（平台机制）
- 部署方式: scp 上传至 ~/staging → node --check 语法验证 → 覆盖 app.js/index.html → 删除旧 nav-item 组件 → touch restart.txt（未生效）→ kill 旧进程由 Passenger 重生（PID 82844）
- 本地源文件: `serve00-catmi/deploy/app.js`、`serve00-catmi/deploy/index.html`
- 验证: https://<你的域名> → 200（服务器侧 + 本地侧）；/api/* → 404（旧 API 已消失）；HTTP 80 → 200
- 回滚: `tar -xzf ~/backup/nav-item-app-2026-09-09.tar.gz -C ~/domains/<你的域名>/` 后 touch tmp/restart.txt

## 备注

- 站点类型保持 nodejs（Passenger）——**改回 PHP 会危及 SSL 绑定，禁止**
- Cloudflare 侧配置不在本机管理范围（<free-ddns-provider> + CF 代理），如需强制 HTTPS 跳转请在 CF 面板配置
- RSS 测试备忘: feeds.bbci.co.uk 旧端点 404，第二阶段需重选有效源（如 Reuters/Al Jazeera/GitHub 上的 RSSHub 实例等）
