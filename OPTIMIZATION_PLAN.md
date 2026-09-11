# OPTIMIZATION_PLAN (R11)

## 硬约束
仅复用现有 auth.js scrypt/session; 不改 DB schema; 不改 MCP 协议与工具; 不改环境变量名; flags 用文件不用表; 每步 node --check + MCP 回归 + 提交。

## Phase 3 认证与开关 (app.js + web/login.html + lib/flags.js + admin 设置页)
1. lib/flags.js: 读 news-data/state/feature-flags.json (10s TTL), 默认 {public_rest:true, web_search_api:false, ui_gate:true}; 异常/缺文件→默认+告警日志。
2. Web 门: GET 静态 → ui_gate=true 时无有效 session 则 302 /login.html; 白名单: /login.html /api/auth/* /api/health。login.html 复用现有登录 UI 风格, 失败统一文案, 服务端 scrypt 校验, 复用 auth.login 会话。
3. /api/search: web_search_api=true 时要求 Bearer(复用 api_tokens 校验)或有效 session; 拒绝→401; 保留既有限流。
4. public_rest=false → 除 health/auth 外 /api/* 一律 403。
5. Admin 设置页加三个开关(现有 session+CSRF 保护, 写 flags.json)。
6. 测试矩阵: 未登录/, 登录, 刷新, 登出, 过期, /api/search 无/有 token, MCP 5 工具回归, admin 回归。

## Phase 4 经济召回
1. SQL 落实覆盖矩阵: sources 按分类; 19 条经济查询对 articles/stories 计数(结果数/新鲜度/来源多样性/官方比例) → 记入 REPORT。
2. 来源: 经现有 discovery 增量加 Tier1/2 RSS ~8-12 个(Fed/ECB/BIS/IMF/Reuters/Yahoo Finance/SCMP business/一财等), 逐个验证抓取成功后再下一个; 不批量。
3. 查询扩展: query.js 加经济词 zh→en 映射表(仅命中经济关键词时扩展, 上限 2 个扩展词), 结果合并去重走现有 toSearchEvidence。
4. 分类: 复用 category 列, 经济子标签由关键词规则打('economy' 系), 不新增字段。
5. 不做: 自动 deep_search、并行 read_url、无限加源。

## Phase 5 报告
OPTIMIZATION_REPORT.md: 认证 6 项 PASS/FAIL + API 8 端点 + MCP 9 工具回归 + 19 条经济查询逐项(数量/新鲜度/来源多样性/官方/国际/中文比例/聚合)。

## 回滚
每 Phase 一个 commit; flags.json 删除即回默认; ui_gate 关闭即恢复公开 UI; DB 无改动故无迁移风险。
