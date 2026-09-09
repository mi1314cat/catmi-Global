# ADMIN — 管理员手册（2026-09-09）

## 登录
- URL: https://<你的域名> → 右上「登录」
- 首次管理员凭据：服务器 `~/news-project/admin-credentials.txt`（600；密码已在交付时一次性展示，请登录后立即在「用户」页重置）
- 登录失败 5 次/IP → 锁 15 分钟

## 管理后台（登录后「管理后台」按钮）
| 页 | 能力 |
|---|---|
| 概览 | 文章/事件/媒体/来源计数 + 7 组件真实状态灯 + 磁盘条 + 24h 错误 |
| 系统状态 | 组件级明细（采集器/队列/DB/存储/REST/MCP/搜索/来源） |
| 搜索服务 | Query Service 状态；网络搜索主路径；SearXNG 接入说明 |
| 情报采集 | 采集器状态/队列/错误 + 排查指引 |
| 来源 | 每源：类型/语言/状态/24h 产量/失败数；操作：测试（单源实测一次）/停用/启用/删除（二次确认，已采集文章保留） |
| MCP 服务 | 状态/Endpoint/复制地址/复制 Agent 配置/创建 Token（仅显示一次）/撤销/恢复/删除/调用统计/工具清单/测试 MCP（9 项健康检查） |
| API | 公开只读端点 / 管理 API / 认证 API 清单 |
| 用户 | 创建用户（普通/管理员）/ 重置密码 / 禁用启用 |
| 存储 | 磁盘使用/分目录大小/保留策略（正文 72h/元数据 30d/事件 90d+） |
| 日志 | 审计日志（管理操作留痕）+ Web 日志 + 采集日志（尾部） |
| 系统诊断 | 16 项检查（HTTPS/DB/权限/目录/UI/REST/MCP/搜索/采集/调度/存储/DNS…）+ 复制报告 |
| 设置 | 只读展示配置与 AI Provider 状态 |

## 运维命令（服务器侧）
```sh
# 重置管理员密码（CLI 直接改库, 服务器上执行）
cd ~/domains/<你的域名>/public_nodejs
node -e 'const a=require("./lib/auth");const r=a.resetUserPassword(1,"新密码至少8位");console.log(r)'
# 查看全部用户
node -e 'console.log(require("./lib/auth").listUsers())'
# 清空全部会话（强制所有登录失效）
node -e 'require("./lib/auth").db().prepare("DELETE FROM sessions").run()'
# 创建 MCP token（CLI, 无需 UI）
node -e 'console.log(require("./lib/auth").createMcpToken("agent-vps"))'
```

## 安全须知
- 密码/token 永不明文入库；token 只显示一次
- 停用用户 = 禁止登录 + 全部会话失效
- 审计日志记录所有管理动作（谁/何时/做了什么）
