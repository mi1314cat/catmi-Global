# WORKLOG — 工作日志（供后续 Agent 快速接手）

> 项目本质: **Global Intelligence & Agent Web Search 基础设施**（不是新闻网站）
> 站点: https://<你的域名> · 服务器: s12.serv00.com · 本地工作区: /root/deepseek1/serve00-catmi/

## 2026-09-09 Phase A（建成 v1）— 已完成
- Phase 0-5: 环境实测 → 采集管道（49 源 4 类型）→ 正文/图片提取 → 去重/事件聚类/趋势 → REST API 11 端点 → MCP（8 工具）
- 生产 cron（run/cleanup/backup/doctor）· 生产验收审计（11 bug 修复: FTS5 UPSERT、调度饥饿、视频聚类门、LIKE 兜底、单锚点误聚等）
- 文档: 15 份必交付 + 审计三件套（CURRENT_STATUS / SOURCE_INVENTORY / PRODUCTION_AUDIT）

## 2026-09-09 Phase B（Global Intelligence 升级）— 本次
### 新增能力
1. **Web Search**（web/lib/websearch.js）: 5 个 keyless provider（ddg/bing/gnews/bingnews/wikipedia）+ 可插拔 SearXNG PRIMARY（env.local 的 SEARXNG_URL）；并发查询/逐 provider 状态/跨源去重/独立降级——零 API Key、零新增依赖。服务器实测: 英文/中文查询返回真实结果；provider 间歇封禁时自动降级。
2. **URL Reader**（news/reader.py + web/lib/reader.js）: 复用管道 Fetcher + extract_html 三级链（trafilatura→Scrapling）；Node 侧 spawn 子进程（并发≤2, 25-45s 硬超时）；状态语义 ok/inaccessible/needs_js/failed；不绕过任何访问控制；Crawl4AI 不默认。实测 Guardian 3978 字符/2.0s。
3. **Unified Query Service**（web/lib/query.js）: REST/MCP/UI 共享；scope=web|intelligence|all；deep_search 确定性多步研究（web→读页→库关联, 40s 预算, 无 AI）。
4. **MCP 扩容 8→12 工具**: +web_search / read_url / search_intelligence / deep_search（§详见 MCP_TOOLS.md）。
5. **REST 扩容**: /api/search（统一三 scope）/ /api/media；/api/status 增加 mcp 真实状态+web_search 配置+组件级磁盘；sources 增加 24h 产量/失败数。
6. **Web Console 重定位**（public/index.html 重写）: Overview（Trending Events + System Overview + Agent Access + Collector + Storage）/ Search（Web/Intelligence/All 三 scope, 结果带 WEB/INTELLIGENCE 标签）/ Events（时间线）/ Sources（可筛选表格）/ Media（元数据+事件关联）/ System（真实组件状态）。全部数据来自生产库与实时状态, 零假数据。
### 本轮修复的 bug
- MCP async 工具返回 Promise → JSON.stringify 得 "{}"（加 await）
- websearch provider 错误分支名字错位
- deep_search intelligence_matches 结构（补 total）
- reader.py Fetcher.get 签名不匹配
### 决策记录
- SearXNG 不上 Serve00（常驻服务 RAM/进程约束）→ 做成可插拔 PRIMARY（SEARCH_ARCHITECTURE.md §1）；需要时 VPS 部署后一行配置切换
- URL Reader 走 Python 子进程复用现有 venv（零新依赖）而非 Node 重写提取器
- deep_search 无 AI（确定性编排 + 预算控制）

## 下一阶段（建议）
- [ ] 地域补源 11 个（SOURCE_INVENTORY §6 清单, 先实测后入册）
- [ ] SEARXNG_URL 配置（用户提供 VPS 后一行切换 PRIMARY）
- [ ] 视频元数据 platform 列 + transcript 字段预留
- [ ] hn-frontpage 退役（与 Algolia 冗余）
- [ ] 72h 生命周期复验（audit1.sh 重跑）
- [ ] 深挖: entities/locations 确定性规则填充（Event 页的 7 Countries 类指标）

## 绝对不能随意改的东西
- 域名绑定 + SSL（SSL 证书有效至 2041；禁 `devil ssl`/`devil www del/add`）
- `~/backup/`（保护目录）
- 生产 cron 表（`crontab -l` 4 条）与 lockf 锁文件约定
- env.local 权限 600；秘密绝不入任何文档/Git/日志
- FTS5 虚拟表写入必须 DELETE+INSERT（UPSERT 会静默失败）
- Passenger 改代码后必须 kill node 进程（无自动 reload）

## 2026-09-09 补充: 外部研究整合（search-research/REPORT.md → SEARCH_RESEARCH_FULL.md）
- 关键实证: 公共 SearXNG JSON 仅 2/78 可用（4次/h/IP 限制）; DDG html 数据中心 IP=CAPTCHA 死; ddgs/argo 为下阶段 Python 侧候选
- SEARCH_ARCHITECTURE.md §8 已更新; SEARXNG_URL 一行即可指向 2 个实测可用公共实例或未来 VPS

## 2026-09-09 第二阶段产品化（中文优先 + 登录 + MCP 管理 + 诊断）— 本轮
### 新增
- **认证系统**: auth.db（独立小库, 尊重管道单写者）; scrypt 密码哈希; DB 会话(HttpOnly/Secure/SameSite=Lax/7d); 登录限速(5 次/IP→15min); CSRF 头校验; admin/user 两级服务端强制; bootstrap admin 自动生成（credentials 文件 600）
- **MCP Token 管理**: 具名 Token 仅哈希入库（sha256+前缀）; 创建仅显示一次; 撤销/恢复/删除/调用统计; MCP 认证顺序 env→DB
- **管理后台 14 页**: 概览/系统状态/搜索服务/情报采集/事件/来源(测试/停用/删除)/媒体/MCP 服务/API/用户/存储/日志/系统诊断(16 项)/设置
- **中文优先 UI**: 全界面中文, 内容保持原文（页脚声明）; 搜索五范围(全部/互联网/情报库/事件/媒体); 结果标签 互联网/情报库/事件
- **SSRF 防护**: read_url 解析全 A/AAAA 拒绝私网/本地/metadata（7/7 实测拦截）; Content-Type 白名单; 5MB 上限
- **单源测试 CLI**: news/source_test.py（管理后台"测试"按钮后端）
### 修复
- newsdb LIKE 分支丢基础 where 条件（column index out of range）→ 重写条件拼接
- UI 部署目录错误（index.html 落根目录）→ 修正 public/
- file:// scheme 拒绝消息带 url 字段
### 验收全过
- 认证: 未登录 403 / 错密码 401 / CSRF 无头 403 / admin API 200
- Token: DB token 调 MCP 12 工具 / 撤销→401 / call_count+1 / 删除清理
- MCP 自测 9/9（Initialize/Tools/web_search 实调/Origin 403/无认证 401）
- 系统诊断 16/16
- UI 中文 5 特征串匹配; media?q 修复后正常
### 管理员凭据
admin / <管理员密码已重置，请勿发布>（已一次性交付; 建议登录后重置; 服务器留档 admin-credentials.txt 600）
