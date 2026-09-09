# SECURITY — 安全模型与合规红线

> 原则: 秘密零入文档（本文只描述机制, 无任何真实值）；服务面最小化；AI 永不进核心链路。

## 1. 秘密管理
| 秘密 | 位置 | 权限 | 出现规则 |
|---|---|---|---|
| MCP_TOKEN | ~/news-project/env.local | 600 | 仅进程内存；永不入 Git/文档/日志/报告 |
| AI_API_KEY（可选） | 同上 env.local | 600 | 仅 AI Provider 插件读；核心链路零依赖 |
| 账号密码 | 不在服务器任何文件 | — | 仅本人使用（部署时人肉输入） |

- env.local 读取代码（web/app.js readToken / config.py get()）**从不打印值**
- 日志脱敏：只记 ip/method/path/状态码/耗时；**不记 Authorization 头、query、body**

## 2. 网络暴露面（唯一公网入口 = Passenger 服务）
| 面 | 防护 |
|---|---|
| /api/* | 公开只读；120 req/min/IP 限速（429）；无写端点 |
| /mcp | Bearer 必需（401 + WWW-Authenticate）；60 req/min/IP；Origin 白名单（仅本站, 缺失放行=规范）；Host 校验（防 DNS 重绑定）；256KB body 上限（413） |
| 静态文件 | 路径规范化 + 前缀校验（防 ../ 遍历）；图片仅限 images 目录内 |
| 管理面 | **不暴露**——运维走 SSH + newsctl（init/backup/restore/doctor/cleanup/update/uninstall） |

## 3. MCP 工具安全（只读边界）
- 8 个工具全部 SELECT 查询；**无 shell/exec/写/删除/安装工具**
- 工具错误 → isError:true 文本返回（不泄漏栈/路径）
- 每请求新建无状态 server+transport（无会话固定攻击面）
- 2026-07-28 规范新增头校验（MCP-Protocol-Version 等）已在 SDK 路线图（MCP.md §1）

## 4. 采集侧合规（法律红线, SOURCE_STRATEGY §3 摘要）
- 描述性 UA + 每域 1.2s 延迟 + 条件 GET + 并发 1 + 退避重试（403/429 不硬爬）
- 绝不绕过 CAPTCHA/登录墙/付费墙/CF 挑战
- 视频只存元数据（不落地媒体流）；robots 灰区端点（YouTube/Reddit/GNews feed）极低频+元数据
- 版权：正文 72h 后只留元数据；展示层全链来源署名（源名+URL+时间）

## 5. 供应链
- Python 依赖: trafilatura/curl_cffi/httpx/feedparser/scrapling（FreeBSD 源码构建验证过版本锁定）
- Node 依赖: 仅 @modelcontextprotocol/sdk@1.30.0 + zod（官方, 94 包 29M）——**零框架路由自写**（app.js）
- 无人值守更新策略: 手动 `serve00-init.sh update`（锁定版本, 不自动升级）

## 6. 故障恢复（DEPLOYMENT.md 详述）
- DB 损坏 → newsctl doctor（quick_check）+ restore 最近备份
- Passenger crash → 按需自动重生（已实测）
- 管道 crash → cron 每 10min 重入 + lockf 防重 + 任务队列断点续跑
