# MCP — MCP 服务总文档（2026-09-09 v2）

> 端点 https://<你的域名>/mcp · 协议 Streamable HTTP（无状态+JSON 响应）· 只读
> 认证：Bearer Token —— ① env bootstrap token（兼容保留）② 管理后台具名 Token（推荐, 仅哈希入库）
> 详细工具 schema 与安全机制见 MCP_TOOLS.md；管理操作见 ADMIN.md；Token 安全细节见 SECURITY_AUDIT.md

## Agent 接入（复制即用）
```json
{"mcpServers":{"global-intelligence":{"url":"https://<你的域名>/mcp","headers":{"Authorization":"Bearer <你的Token>"}}}}
```
Token 获取：管理员登录 → MCP 服务 → 创建 Token（弹窗仅显示一次）。

## 工具（12, 全部只读）
web_search / deep_search / read_url / search_intelligence / search_news / search_events /
get_event / get_timeline / get_article / search_media / get_trending / list_sources

## Token 生命周期
创建（明文一次）→ 使用（last_used/call_count 自动记录）→ 撤销（立即 401）→ 恢复/删除。
实测：DB token 调 tools/list 12 工具 ✓；撤销后 401 ✓；调用统计 +1 ✓。

## 管理健康检查（管理后台「测试 MCP」, 9 项）
Endpoint / HTTPS / Authentication 配置 / Initialize / Tools/List / web_search 实调 /
search_intelligence 实调 / Origin Validation（伪造 Origin→403）/ 无认证拒绝（→401）。
当前生产实测：9/9 通过。
