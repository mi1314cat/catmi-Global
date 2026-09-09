# SECURITY_AUDIT — 安全审计（2026-09-09 第二阶段产品化后 v2）

## 1. 认证方案（本阶段新增）
| 项 | 实现 | 验收证据 |
|---|---|---|
| 密码存储 | Node 内置 crypto.scryptSync(N=16384,r=8,p=1)+16B 随机盐，只存 `scrypt$N$r$p$salt$hash`；明文永不入库/日志/git | DB 检查：users 表仅 pass_hash |
| 会话 | 24 字节随机 sid；DB 持久化（Passenger 重启不失效）；7 天过期（登录时顺手清理过期） | 登录→me→logout 全链实测 |
| Cookie | `gi_session` HttpOnly + Secure + SameSite=Lax + Max-Age 7d + Path=/ | Set-Cookie 头实测 |
| 登录防爆破 | 同 IP 5 次失败 → 15 分钟锁定（内存计数）；失败审计 | login-fail 审计行 |
| CSRF | 全部管理写操作要求 `X-GI-CSRF: <session csrf>` 头（每会话随机）；叠加 SameSite=Lax Cookie | 无头 403 / 带头 200 实测 |
| 权限模型 | admin/user 两级；管理 API 全部服务端校验（非前端隐藏）；user 不可见管理端点 | 未登录 403 / admin 200 |
| bootstrap | 首次启动生成 admin + 随机密码 → `~/news-project/admin-credentials.txt`(600)；密码只展示一次 | 文件 600 实测 |
| 密码重置 | 重置即删除该用户全部会话；admin 账户禁用被拒绝（防锁死） | 代码路径 |

## 2. MCP Token 方案
- DB 表 `mcp_tokens`：只存 **sha256(token_hash)** + 前 11 位前缀；**明文仅创建响应一次**
- 多 Token 并存：名称/创建时间/最后使用/调用次数/启用/撤销/删除（全部实测）
- 认证顺序：env bootstrap MCP_TOKEN（保留兼容）→ DB token（新增）；撤销即时生效（无缓存）
- 每次使用更新 last_used_at + call_count
- 旧共享 token 模式仍可用（bootstrap），但推荐迁移到具名 token

## 3. SSRF 防护（read_url，本阶段新增）
`_assert_public_host`：DNS 解析全部 A/AAAA → 拒绝 loopback/private/link-local/reserved/multicast/unspecified + localhost/*.local/*.internal + 非 http(s) scheme。实测 7/7 拦截（127.0.0.1:8080 / localhost / 169.254.169.254 metadata / 10.0.0.1 / ::1 / 192.168.1.1 / fe80::）；正常公网页面不受影响。
附加护栏：Content-Type 白名单（text/html/plain/xml/json）、响应上限 5MB、子进程硬超时、并发≤2。

## 4. MCP 安全（保持 + 增强）
HTTPS-only · Bearer（env token 或 DB token）· Origin 白名单（伪造 Origin→403 实测）· 无认证→401 实测 · 60 req/min/IP · body≤256KB · 只读工具（无 shell/exec/写文件/写库/重启/安装）· 日志脱敏（无 Authorization/body/query）· Host 校验。

## 5. 秘密清单（存放位置与权限）
| 秘密 | 位置 | 权限 |
|---|---|---|
| catmi SSH 密码 | 本地 /tmp/pw_catmi.txt（600，会话后清理） | 600 |
| MCP bootstrap token | ~/news-project/env.local | 600 |
| 管理员初始密码 | ~/news-project/admin-credentials.txt | 600 |
| DB tokens | auth.db（哈希） | 600 目录 |
规则：任何秘密不进 git/文档/前端 bundle/日志；页面 token 仅创建弹窗一次。

## 6. 已知限制（诚实记录）
- 会话在 auth.db（不加密磁盘）——若主机文件被读取则 7 天内会话可重放（个人主机威胁模型下可接受；可用重启清表缓解：`DELETE FROM sessions`）
- 无 2FA（个人基础设施阶段未实现；可用强密码+IP 限速缓解）
- HTTPS 内部跳为 Passenger 明文（nginx 终止 TLS）——Cookie Secure 依赖浏览器侧 https-only 行为
- 管理写操作直写 news.db sources 表（独立可写连接 + busy_timeout=5000）——与 cron 管道的 WAL 并发已按 busy_timeout 容错，极端情况写冲突报错不破坏数据
- 登录限速为进程内存（Passenger 重启清零）——暴力破解窗口极小但存在
